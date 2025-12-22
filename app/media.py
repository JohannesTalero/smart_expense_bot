"""Módulo de procesamiento multimedia (audio e imágenes).

Utiliza OpenAI Whisper para transcripción de audio y GPT-4o Vision
para extracción de datos de recibos.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cliente OpenAI global (singleton)
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """
    Obtiene o crea el cliente de OpenAI (singleton).
    
    Returns:
        Cliente de OpenAI configurado.
    """
    global _openai_client
    
    if _openai_client is None:
        settings = get_settings()
        _openai_client = OpenAI(api_key=settings.openai_api_key)
        logger.info("Cliente de OpenAI inicializado")
    
    return _openai_client


async def descargar_archivo_telegram(file_id: str) -> bytes:
    """
    Descarga un archivo de Telegram usando su file_id.
    
    Args:
        file_id: ID del archivo en Telegram.
    
    Returns:
        Contenido del archivo como bytes.
    
    Raises:
        Exception: Si hay un error descargando el archivo.
    """
    settings = get_settings()
    
    # Paso 1: Obtener la ruta del archivo
    get_file_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(get_file_url, params={"file_id": file_id})
        
        if response.status_code != 200:
            raise Exception(f"Error obteniendo info del archivo: {response.status_code}")
        
        data = response.json()
        
        if not data.get("ok"):
            raise Exception(f"Error en respuesta de Telegram: {data}")
        
        file_path = data["result"]["file_path"]
        
        # Paso 2: Descargar el archivo
        download_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
        
        file_response = await client.get(download_url)
        
        if file_response.status_code != 200:
            raise Exception(f"Error descargando archivo: {file_response.status_code}")
        
        logger.info(f"Archivo descargado: {file_path} ({len(file_response.content)} bytes)")
        return file_response.content


def transcribir_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """
    Transcribe un archivo de audio usando OpenAI Whisper.
    
    Args:
        audio_bytes: Contenido del audio como bytes.
        filename: Nombre del archivo (para determinar formato).
    
    Returns:
        Texto transcrito del audio.
    
    Raises:
        Exception: Si hay un error en la transcripción.
    """
    client = get_openai_client()
    
    # Crear archivo temporal para pasar a la API
    # La API de Whisper necesita un archivo con nombre
    suffix = Path(filename).suffix or ".ogg"
    
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(audio_bytes)
        temp_path = temp_file.name
    
    try:
        with open(temp_path, "rb") as audio_file:
            # Usar la API de Whisper para transcribir
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es",  # Especificar español para mejor precisión
            )
        
        texto = transcript.text.strip()
        logger.info(f"Audio transcrito: '{texto[:50]}...' ({len(texto)} caracteres)")
        return texto
    
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}", exc_info=True)
        raise
    finally:
        # Limpiar archivo temporal
        try:
            Path(temp_path).unlink()
        except Exception:
            pass


async def transcribir_audio_telegram(file_id: str) -> str:
    """
    Descarga y transcribe un archivo de audio de Telegram.
    
    Flujo completo: file_id → descargar → transcribir → texto
    
    Args:
        file_id: ID del archivo de audio en Telegram.
    
    Returns:
        Texto transcrito del audio.
    
    Raises:
        Exception: Si hay un error en el proceso.
    """
    logger.info(f"Procesando audio de Telegram: {file_id}")
    
    # Descargar el archivo
    audio_bytes = await descargar_archivo_telegram(file_id)
    
    # Transcribir (función síncrona, se ejecutará en el thread pool)
    texto = transcribir_audio(audio_bytes)
    
    return texto

