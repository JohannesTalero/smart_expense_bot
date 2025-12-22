"""Aplicación principal FastAPI para el Smart Expense Bot."""

import logging
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, Header
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


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Endpoint de salud para verificar que el servidor está vivo."""
    return {"status": "ok", "message": "Servidor funcionando correctamente"}


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """
    Endpoint que recibe updates de Telegram.
    Por ahora responde con un mensaje simple de confirmación.
    """
    try:
        # Obtener el body del request
        update_data: Dict[str, Any] = await request.json()
        logger.info(f"Update recibido: {update_data}")

        # Verificar que es un mensaje válido
        if "message" not in update_data:
            logger.warning("Update sin campo 'message'")
            return JSONResponse(
                content={"ok": True, "message": "Update recibido (sin mensaje)"}
            )

        message = update_data["message"]
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")

        # Validar usuario autorizado
        if user_id and not settings.is_user_allowed(user_id):
            logger.warning(f"Usuario no autorizado: {user_id}")
            return JSONResponse(
                content={"ok": True, "message": "Usuario no autorizado"},
                status_code=403,
            )

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
    return {
        "message": "Smart Expense Bot API",
        "version": "0.1.0",
        "status": "running",
    }

