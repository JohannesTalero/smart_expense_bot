"""Aplicación principal FastAPI para el Smart Expense Bot."""

import asyncio
import logging
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent import procesar_mensaje
from app.config import get_settings
from app.media import procesar_imagen_telegram, transcribir_audio_telegram

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Inicializar FastAPI
app = FastAPI(
    title="Smart Expense Bot",
    description="Bot de Telegram para gestión de finanzas personales con IA",
    version="0.1.0",
)

# Obtener configuración
settings = get_settings()

# Variable global para la tarea de polling
polling_task: Optional[asyncio.Task] = None

# ============ Buffer de mensajes (debounce) ============
# Tiempo de espera antes de procesar mensajes acumulados (segundos)
MESSAGE_BUFFER_DELAY = 3.0

# Almacena mensajes pendientes por chat_id: {chat_id: [{"text": ..., "user_name": ..., ...}, ...]}
pending_messages: dict[int, list[dict[str, Any]]] = {}

# Almacena los timers activos por chat_id: {chat_id: asyncio.Task}
pending_timers: dict[int, asyncio.Task] = {}

# Lock para evitar race conditions
buffer_lock = asyncio.Lock()


async def process_buffered_messages(chat_id: int) -> None:
    """
    Procesa los mensajes acumulados de un chat después del delay.
    Concatena todos los mensajes de texto y los envía al agente.
    """
    async with buffer_lock:
        messages = pending_messages.pop(chat_id, [])
        pending_timers.pop(chat_id, None)

    if not messages:
        return

    # Usar datos del primer mensaje para user_name
    first_msg = messages[0]
    user_name = first_msg["user_name"]

    # Concatenar todos los textos
    combined_text = " ".join(msg["text"] for msg in messages if msg.get("text"))

    logger.info(
        f"Procesando {len(messages)} mensaje(s) acumulados de {user_name}: '{combined_text[:80]}...'"
    )

    try:
        # Procesar el mensaje combinado con el agente LLM
        response_text = await asyncio.to_thread(
            procesar_mensaje,
            texto=combined_text,
            user=user_name,
        )

        # Enviar respuesta a Telegram
        telegram_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

        async with httpx.AsyncClient() as client:
            await client.post(
                telegram_url,
                json={
                    "chat_id": chat_id,
                    "text": response_text,
                },
            )

        logger.info(f"Respuesta enviada a chat {chat_id}")

    except Exception as e:
        logger.error(f"Error procesando mensajes acumulados: {e}", exc_info=True)
        try:
            telegram_url = (
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            )
            async with httpx.AsyncClient() as client:
                await client.post(
                    telegram_url,
                    json={
                        "chat_id": chat_id,
                        "text": "Miau... 😿 Algo salió mal. Por favor intenta de nuevo.",
                    },
                )
        except Exception as send_error:
            logger.error(f"Error enviando mensaje de error: {send_error}", exc_info=True)


async def schedule_buffer_processing(chat_id: int) -> None:
    """
    Programa el procesamiento de mensajes después del delay.
    Si ya hay un timer, lo cancela y crea uno nuevo (debounce).
    """
    async with buffer_lock:
        # Cancelar timer existente si hay uno
        if chat_id in pending_timers:
            pending_timers[chat_id].cancel()
            try:
                await pending_timers[chat_id]
            except asyncio.CancelledError:
                pass

        # Crear nuevo timer
        async def delayed_process():
            await asyncio.sleep(MESSAGE_BUFFER_DELAY)
            await process_buffered_messages(chat_id)

        pending_timers[chat_id] = asyncio.create_task(delayed_process())


async def process_update(update_data: dict[str, Any]) -> None:
    """
    Procesa un update de Telegram (compartido entre webhook y polling).

    Soporta:
    - Mensajes de texto (con buffer/debounce para mensajes fragmentados)
    - Notas de voz (audio) - procesamiento inmediato
    - Fotos/imágenes (recibos) - procesamiento inmediato
    """
    chat_id = None
    try:
        # Verificar que es un mensaje válido
        if "message" not in update_data:
            logger.debug("Update sin campo 'message'")
            return

        message = update_data["message"]
        chat_id = message.get("chat", {}).get("id")
        user_data = message.get("from", {})
        user_id = user_data.get("id")

        # Obtener nombre del usuario de Telegram
        # Prioridad: first_name + last_name > first_name > username > user_id
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        username = user_data.get("username", "")

        if first_name and last_name:
            user_name = f"{first_name} {last_name}"
        elif first_name:
            user_name = first_name
        elif username:
            user_name = username
        else:
            user_name = str(user_id) if user_id else "Usuario"

        text = message.get("text", "")
        caption = message.get("caption", "")  # Caption de fotos/documentos

        # Detectar tipo de mensaje
        voice = message.get("voice")  # Nota de voz
        audio = message.get("audio")  # Archivo de audio
        photo = message.get("photo")  # Lista de fotos (diferentes tamaños)
        document = message.get("document")  # Documento (puede ser imagen)

        logger.info(
            f"Mensaje de {user_name} (ID: {user_id}): texto='{text[:50] if text else '(vacío)'}', voice={bool(voice)}, photo={bool(photo)}"
        )

        # Validar usuario autorizado
        if user_id and not settings.is_user_allowed(user_id):
            logger.warning(f"Usuario no autorizado: {user_id}")
            # Enviar mensaje de no autorizado
            if chat_id:
                telegram_url = (
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
                )
                async with httpx.AsyncClient() as client:
                    await client.post(
                        telegram_url,
                        json={
                            "chat_id": chat_id,
                            "text": "Miau... 🐱 Lo siento, no estás autorizado para usar este bot.",
                        },
                    )
            return

        # Procesar audio (nota de voz o archivo de audio)
        if voice or audio:
            audio_data = voice or audio
            file_id = audio_data.get("file_id")

            if file_id:
                logger.info(f"Procesando audio: file_id={file_id}")

                # Notificar al usuario que estamos procesando
                telegram_url = (
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendChatAction"
                )
                async with httpx.AsyncClient() as client:
                    await client.post(
                        telegram_url,
                        json={"chat_id": chat_id, "action": "typing"},
                    )

                try:
                    # Transcribir el audio
                    text = await transcribir_audio_telegram(file_id)
                    logger.info(f"Audio transcrito: '{text[:50]}...'")
                except Exception as e:
                    logger.error(f"Error transcribiendo audio: {e}", exc_info=True)
                    response_text = (
                        "Mrrrow... 😿 No pude entender ese audio. "
                        "¿Puedes intentar de nuevo o escribirme el mensaje?"
                    )
                    # Enviar respuesta de error y salir
                    telegram_url = (
                        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
                    )
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            telegram_url,
                            json={"chat_id": chat_id, "text": response_text},
                        )
                    return

        # Procesar imagen (foto o documento de imagen)
        if photo or (document and document.get("mime_type", "").startswith("image/")):
            # Obtener file_id de la imagen con mejor resolución
            if photo:
                # photo es una lista ordenada por tamaño, tomamos la última (más grande)
                file_id = photo[-1].get("file_id")
            else:
                file_id = document.get("file_id")

            if file_id:
                logger.info(f"Procesando imagen: file_id={file_id}")

                # Notificar al usuario que estamos procesando
                telegram_url = (
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendChatAction"
                )
                async with httpx.AsyncClient() as client:
                    await client.post(
                        telegram_url,
                        json={"chat_id": chat_id, "action": "typing"},
                    )

                try:
                    # Extraer datos del recibo
                    datos_recibo = await procesar_imagen_telegram(file_id)
                    logger.info(f"Recibo extraído: {datos_recibo}")

                    # Construir texto para el agente basado en los datos extraídos
                    # Si hay caption, lo usamos como contexto adicional
                    if caption:
                        text = f"Registrar gasto de {datos_recibo['monto']} en {datos_recibo['categoria'].lower()}. Descripción: {datos_recibo['descripcion']}. {caption}"
                    else:
                        establecimiento_info = (
                            f" en {datos_recibo['establecimiento']}"
                            if datos_recibo.get("establecimiento")
                            else ""
                        )
                        text = f"Registrar gasto de {datos_recibo['monto']} en {datos_recibo['categoria'].lower()}{establecimiento_info}. Descripción: {datos_recibo['descripcion']}"

                    # Agregar nota de confianza si es baja
                    if datos_recibo["confianza"] < 0.7:
                        text += " (Nota: el recibo no estaba muy claro, verifica los datos)"

                    logger.info(f"Texto construido desde recibo: '{text}'")

                except Exception as e:
                    logger.error(f"Error procesando imagen: {e}", exc_info=True)
                    response_text = (
                        "Mrrrow... 😿 No pude leer ese recibo. "
                        "¿Puedes tomar una foto más clara o escribirme el gasto?"
                    )
                    # Enviar respuesta de error y salir
                    telegram_url = (
                        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
                    )
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            telegram_url,
                            json={"chat_id": chat_id, "text": response_text},
                        )
                    return

        # Si no hay texto (ni transcrito), responder con mensaje de ayuda
        if not text:
            response_text = (
                "Miau... 🐱 Envíame un mensaje de texto, nota de voz o foto de recibo para registrar un gasto.\n\n"
                "Ejemplos:\n"
                "• Gasté 20 mil en almuerzo\n"
                "• 50000 en transporte\n"
                "• ¿Cuánto gasté este mes?\n"
                "• Ver presupuesto de comida\n"
                "• 🎤 Envíame una nota de voz\n"
                "• 📸 Envíame una foto del recibo"
            )
            # Mensaje de ayuda se envía inmediatamente
            telegram_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(
                    telegram_url,
                    json={"chat_id": chat_id, "text": response_text},
                )
            return

        # Determinar si el mensaje requiere procesamiento inmediato o puede ir al buffer
        # Audio y fotos ya fueron procesados arriba y tienen texto construido
        is_media_message = bool(voice or audio or photo or (document and document.get("mime_type", "").startswith("image/")))

        if is_media_message:
            # Mensajes con media: procesar inmediatamente
            response_text = await asyncio.to_thread(
                procesar_mensaje,
                texto=text,
                user=user_name,
            )

            telegram_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(
                    telegram_url,
                    json={"chat_id": chat_id, "text": response_text},
                )
            logger.info(f"Respuesta enviada a chat {chat_id}")
        else:
            # Mensajes de texto puro: agregar al buffer (debounce)
            async with buffer_lock:
                if chat_id not in pending_messages:
                    pending_messages[chat_id] = []

                pending_messages[chat_id].append({
                    "text": text,
                    "user_name": user_name,
                    "user_id": user_id,
                })

            # Programar procesamiento (reinicia el timer si ya existe)
            await schedule_buffer_processing(chat_id)
            logger.debug(f"Mensaje agregado al buffer para chat {chat_id}")

    except Exception as e:
        logger.error(f"Error procesando update: {e}", exc_info=True)
        # Enviar mensaje de error al usuario si tenemos chat_id
        if chat_id:
            try:
                telegram_url = (
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
                )
                async with httpx.AsyncClient() as client:
                    await client.post(
                        telegram_url,
                        json={
                            "chat_id": chat_id,
                            "text": "Miau... 😿 Algo salió mal mientras procesaba tu mensaje. Por favor intenta de nuevo.",
                        },
                    )
            except Exception as send_error:
                logger.error(f"Error enviando mensaje de error: {send_error}", exc_info=True)


async def poll_telegram_updates() -> None:
    """
    Consulta Telegram periódicamente por nuevos mensajes (polling mode).
    """
    logger.info("Iniciando modo polling...")
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"

    last_update_id = 0
    consecutive_errors = 0
    max_consecutive_errors = 5

    # Configurar timeout más largo para long polling
    timeout = httpx.Timeout(60.0, connect=10.0)  # 60s total, 10s para conectar

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            try:
                # Preguntar a Telegram por actualizaciones
                response = await client.get(
                    url,
                    params={
                        "offset": last_update_id + 1,
                        "timeout": 30,  # Long polling: espera hasta 30s por nuevos mensajes
                    },
                )

                # Resetear contador de errores en caso de éxito
                consecutive_errors = 0

                if response.status_code != 200:
                    logger.error(f"Error en polling: {response.status_code}")
                    await asyncio.sleep(5)
                    continue

                data = response.json()

                if not data.get("ok"):
                    logger.error(f"Error en respuesta de Telegram: {data}")
                    await asyncio.sleep(5)
                    continue

                updates = data.get("result", [])

                if updates:
                    logger.debug(f"Recibidos {len(updates)} updates")
                    for update in updates:
                        await process_update(update)
                        last_update_id = max(last_update_id, update["update_id"])
                else:
                    # No hay mensajes nuevos, esperar un poco antes de la siguiente consulta
                    await asyncio.sleep(settings.polling_interval)

            except httpx.ReadTimeout:
                # Timeout es normal en long polling cuando no hay mensajes
                # No es un error crítico, solo continuar
                logger.debug("Timeout en polling (normal en long polling)")
                consecutive_errors = 0  # Timeout no cuenta como error
                continue
            except httpx.ConnectTimeout:
                logger.warning("Timeout de conexión en polling, reintentando...")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Demasiados errores consecutivos, esperando más tiempo...")
                    await asyncio.sleep(30)
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                logger.info("Polling cancelado")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error en polling: {e}", exc_info=True)

                # Si hay muchos errores consecutivos, esperar más tiempo
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Demasiados errores consecutivos, esperando más tiempo...")
                    await asyncio.sleep(30)
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event() -> None:
    """Inicia el polling si está habilitado."""
    global polling_task

    if settings.use_polling:
        logger.info("Modo polling habilitado - iniciando...")
        # Eliminar webhook si existe (para evitar conflictos)
        try:
            delete_webhook_url = (
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/deleteWebhook"
            )
            async with httpx.AsyncClient() as client:
                await client.post(delete_webhook_url, json={"drop_pending_updates": True})
            logger.info("Webhook eliminado (modo polling activo)")
        except Exception as e:
            logger.warning(f"No se pudo eliminar webhook: {e}")

        # Iniciar polling en background
        polling_task = asyncio.create_task(poll_telegram_updates())
    else:
        logger.info("Modo webhook activo (polling deshabilitado)")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Detiene el polling al cerrar la aplicación."""
    global polling_task

    if polling_task and not polling_task.done():
        logger.info("Deteniendo polling...")
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        logger.info("Polling detenido")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Endpoint de salud para verificar que el servidor está vivo."""
    mode = "polling" if settings.use_polling else "webhook"
    return {
        "status": "ok",
        "message": "Servidor funcionando correctamente",
        "mode": mode,
    }


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """
    Endpoint que recibe updates de Telegram (modo webhook).
    Solo funciona si use_polling=False.
    """
    if settings.use_polling:
        return JSONResponse(
            content={
                "ok": False,
                "error": "Webhook deshabilitado - modo polling activo",
            },
            status_code=400,
        )

    try:
        # Obtener el body del request
        update_data: dict[str, Any] = await request.json()
        logger.info(f"Update recibido vía webhook: {update_data}")

        # Procesar el update (función compartida)
        await process_update(update_data)

        return JSONResponse(content={"ok": True, "message": "Mensaje procesado"})

    except Exception as e:
        logger.error(f"Error procesando webhook: {e}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "error": str(e)},
            status_code=500,
        )


@app.get("/")
async def root() -> dict[str, str]:
    """Endpoint raíz."""
    mode = "polling" if settings.use_polling else "webhook"
    return {
        "message": "Smart Expense Bot API",
        "version": "0.1.0",
        "status": "running",
        "mode": mode,
    }
