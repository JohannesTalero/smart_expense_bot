"""Aplicación principal FastAPI para el Smart Expense Bot."""

import asyncio
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from app.config import get_settings

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


async def process_update(update_data: Dict[str, Any]) -> None:
    """
    Procesa un update de Telegram (compartido entre webhook y polling).
    """
    try:
        # Verificar que es un mensaje válido
        if "message" not in update_data:
            logger.debug("Update sin campo 'message'")
            return

        message = update_data["message"]
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")

        logger.info(f"Mensaje recibido de usuario {user_id}: {text}")

        # Validar usuario autorizado
        if user_id and not settings.is_user_allowed(user_id):
            logger.warning(f"Usuario no autorizado: {user_id}")
            return

        # Responder con mensaje simple
        response_text = "Mensaje recibido ✓"
        
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
        logger.error(f"Error procesando update: {e}", exc_info=True)


async def poll_telegram_updates() -> None:
    """
    Consulta Telegram periódicamente por nuevos mensajes (polling mode).
    """
    logger.info("Iniciando modo polling...")
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    
    last_update_id = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                # Preguntar a Telegram por actualizaciones
                response = await client.get(
                    url,
                    params={
                        "offset": last_update_id + 1,
                        "timeout": 30,  # Long polling: espera hasta 30s por nuevos mensajes
                    }
                )
                
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
                
            except asyncio.CancelledError:
                logger.info("Polling cancelado")
                break
            except Exception as e:
                logger.error(f"Error en polling: {e}", exc_info=True)
                await asyncio.sleep(5)  # Esperar más si hay error


@app.on_event("startup")
async def startup_event() -> None:
    """Inicia el polling si está habilitado."""
    global polling_task
    
    if settings.use_polling:
        logger.info("Modo polling habilitado - iniciando...")
        # Eliminar webhook si existe (para evitar conflictos)
        try:
            delete_webhook_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/deleteWebhook"
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
async def health_check() -> Dict[str, str]:
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
        update_data: Dict[str, Any] = await request.json()
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
async def root() -> Dict[str, str]:
    """Endpoint raíz."""
    mode = "polling" if settings.use_polling else "webhook"
    return {
        "message": "Smart Expense Bot API",
        "version": "0.1.0",
        "status": "running",
        "mode": mode,
    }

