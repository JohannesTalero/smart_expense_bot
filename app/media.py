"""Módulo de procesamiento multimedia (audio e imágenes).

Utiliza OpenAI Whisper para transcripción de audio y GPT-4o Vision
para extracción de datos de recibos.
"""

import base64
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional, TypedDict

import httpx
from openai import OpenAI

from app.config import get_settings


class DatosRecibo(TypedDict):
    """Estructura de datos extraídos de un recibo."""
    monto: float
    descripcion: str
    categoria: str
    establecimiento: Optional[str]
    fecha: Optional[str]
    confianza: float  # 0.0 a 1.0

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


def extraer_recibo(image_bytes: bytes) -> DatosRecibo:
    """
    Extrae datos de un recibo/factura usando GPT-4o-mini con visión.
    
    Args:
        image_bytes: Contenido de la imagen como bytes.
    
    Returns:
        DatosRecibo con los campos extraídos.
    
    Raises:
        Exception: Si hay un error en la extracción o el JSON es inválido.
    """
    client = get_openai_client()
    
    # Convertir imagen a base64
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    
    # Detectar tipo de imagen (asumimos JPEG por defecto)
    # Los primeros bytes pueden indicar el formato
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        media_type = "image/jpeg"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"  # Default
    
    prompt_sistema = """Eres un asistente experto en extraer información de recibos y facturas.

Analiza la imagen del recibo y extrae la siguiente información en formato JSON:
- monto: El monto total en números (sin símbolos de moneda, solo el número)
- descripcion: Breve descripción de la compra o servicio
- categoria: Una de estas categorías: Comida, Transporte, Entretenimiento, Salud, Hogar, Compras, Servicios, Educación, Otro
- establecimiento: Nombre del comercio o establecimiento (null si no se puede determinar)
- fecha: Fecha del recibo en formato YYYY-MM-DD (null si no se puede determinar)
- confianza: Número entre 0.0 y 1.0 indicando qué tan seguro estás de la extracción

IMPORTANTE:
- Si no puedes leer claramente algún campo, usa tu mejor estimación basándote en el contexto
- El monto debe ser un número decimal (ej: 25000.00)
- La confianza debe reflejar qué tan legible es el recibo

Responde SOLO con el JSON, sin texto adicional ni bloques de código."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": prompt_sistema
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extrae la información de este recibo:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_base64}",
                                "detail": "high"  # Alta resolución para mejor lectura
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.1,  # Baja temperatura para respuestas más consistentes
        )
        
        content = response.choices[0].message.content.strip()
        logger.info(f"Respuesta de GPT-4o-mini vision: {content[:200]}")
        
        # Limpiar posibles bloques de código markdown
        if content.startswith("```"):
            # Remover bloques de código
            content = re.sub(r'^```(?:json)?\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
        
        # Parsear JSON
        datos = json.loads(content)
        
        # Validar y convertir campos
        resultado: DatosRecibo = {
            "monto": float(datos.get("monto", 0)),
            "descripcion": str(datos.get("descripcion", "Compra")),
            "categoria": str(datos.get("categoria", "Otro")),
            "establecimiento": datos.get("establecimiento"),
            "fecha": datos.get("fecha"),
            "confianza": float(datos.get("confianza", 0.5))
        }
        
        # Validar rango de confianza
        resultado["confianza"] = max(0.0, min(1.0, resultado["confianza"]))
        
        logger.info(f"Recibo extraído: ${resultado['monto']} - {resultado['descripcion']} ({resultado['categoria']})")
        return resultado
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parseando JSON de respuesta: {e}")
        raise ValueError(f"No se pudo parsear la respuesta como JSON: {e}")
    except Exception as e:
        logger.error(f"Error extrayendo datos del recibo: {e}", exc_info=True)
        raise


async def procesar_imagen_telegram(file_id: str) -> DatosRecibo:
    """
    Descarga y procesa una imagen de recibo de Telegram.
    
    Flujo completo: file_id → descargar → extraer datos → DatosRecibo
    
    Args:
        file_id: ID de la imagen en Telegram.
    
    Returns:
        DatosRecibo con los datos extraídos del recibo.
    
    Raises:
        Exception: Si hay un error en el proceso.
    """
    logger.info(f"Procesando imagen de Telegram: {file_id}")
    
    # Descargar la imagen
    image_bytes = await descargar_archivo_telegram(file_id)
    
    # Extraer datos del recibo (función síncrona)
    datos = extraer_recibo(image_bytes)
    
    return datos

