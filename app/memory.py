"""Módulo de memoria conversacional usando Redis.

Almacena el historial de conversación por usuario y día, permitiendo
que el agente mantenga contexto durante la conversación.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, message_to_dict, messages_from_dict

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cliente Redis global (se inicializa en get_redis_client)
_redis_client = None


def get_redis_client():
    """
    Obtiene o crea el cliente de Redis (singleton).
    
    Returns:
        Cliente de Redis o None si Redis está deshabilitado.
    """
    global _redis_client
    
    settings = get_settings()
    
    if not settings.redis_enabled:
        logger.debug("Redis deshabilitado en configuración")
        return None
    
    if _redis_client is None:
        try:
            import redis
            
            redis_url = settings.redis_url
            
            # Detectar si es Upstash y convertir redis:// a rediss:// (SSL requerido)
            if "upstash.io" in redis_url and redis_url.startswith("redis://"):
                redis_url = redis_url.replace("redis://", "rediss://", 1)
                logger.info("Detectado Upstash - usando conexión SSL (rediss://)")
            
            # Upstash y otros servicios en la nube requieren SSL
            # redis.from_url detecta automáticamente si la URL usa rediss:// (SSL)
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Probar conexión
            _redis_client.ping()
            logger.info("Cliente de Redis inicializado correctamente")
        except ImportError:
            logger.warning(
                "Redis no está instalado. Instala con: poetry install --extras redis"
            )
            return None
        except Exception as e:
            logger.error(f"Error conectando a Redis: {e}", exc_info=True)
            return None
    
    return _redis_client


def _get_conversation_key(user_id: str, date: Optional[str] = None) -> str:
    """
    Genera la clave Redis para el historial de conversación de un usuario en una fecha.
    
    Args:
        user_id: ID del usuario.
        date: Fecha en formato YYYY-MM-DD. Si es None, usa la fecha actual.
    
    Returns:
        Clave Redis (ej: "conversation:user_123:2024-12-22").
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return f"conversation:{user_id}:{date}"


def _get_today_key(user_id: str) -> str:
    """Obtiene la clave para la conversación de hoy."""
    return _get_conversation_key(user_id)


def save_message(user_id: str, message: BaseMessage) -> bool:
    """
    Guarda un mensaje en el historial de conversación del usuario para hoy.
    
    Args:
        user_id: ID del usuario.
        message: Mensaje de LangChain a guardar.
    
    Returns:
        True si se guardó correctamente, False en caso contrario.
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        key = _get_today_key(user_id)
        
        # Convertir mensaje a dict
        message_dict = message_to_dict(message)
        
        # Agregar timestamp
        message_dict["_timestamp"] = datetime.now().isoformat()
        
        # Agregar a la lista (usando RPUSH)
        client.rpush(key, json.dumps(message_dict))
        
        # Establecer TTL de 25 horas (para mantener conversaciones del mismo día)
        # Esto asegura que las conversaciones se eliminen después de medianoche
        client.expire(key, 25 * 60 * 60)
        
        logger.debug(f"Mensaje guardado para usuario {user_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error guardando mensaje en Redis: {e}", exc_info=True)
        return False


def get_conversation_history(
    user_id: str,
    max_messages: int = 20,
    date: Optional[str] = None,
) -> List[BaseMessage]:
    """
    Obtiene el historial de conversación del usuario para una fecha específica.
    
    Args:
        user_id: ID del usuario.
        max_messages: Número máximo de mensajes a retornar (los más recientes).
        date: Fecha en formato YYYY-MM-DD. Si es None, usa la fecha actual.
    
    Returns:
        Lista de mensajes de LangChain (HumanMessage y AIMessage).
    """
    client = get_redis_client()
    if client is None:
        return []
    
    try:
        key = _get_conversation_key(user_id, date)
        
        # Obtener todos los mensajes
        messages_json = client.lrange(key, 0, -1)
        
        if not messages_json:
            return []
        
        # Convertir JSON a dicts y luego a mensajes de LangChain
        messages = []
        for msg_json in messages_json:
            try:
                msg_dict = json.loads(msg_json)
                # Remover timestamp interno antes de convertir
                msg_dict.pop("_timestamp", None)
                # Convertir dict a mensaje de LangChain
                msg = messages_from_dict([msg_dict])[0]
                messages.append(msg)
            except Exception as e:
                logger.warning(f"Error parseando mensaje desde Redis: {e}")
                continue
        
        # Retornar los últimos max_messages
        return messages[-max_messages:] if len(messages) > max_messages else messages
    
    except Exception as e:
        logger.error(f"Error obteniendo historial de Redis: {e}", exc_info=True)
        return []


def clear_conversation_history(user_id: str, date: Optional[str] = None) -> bool:
    """
    Limpia el historial de conversación del usuario para una fecha específica.
    
    Args:
        user_id: ID del usuario.
        date: Fecha en formato YYYY-MM-DD. Si es None, usa la fecha actual.
    
    Returns:
        True si se limpió correctamente, False en caso contrario.
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        key = _get_conversation_key(user_id, date)
        deleted = client.delete(key)
        logger.info(f"Historial limpiado para usuario {user_id} (fecha: {date or 'hoy'})")
        return deleted > 0
    
    except Exception as e:
        logger.error(f"Error limpiando historial de Redis: {e}", exc_info=True)
        return False


def cleanup_old_conversations(days_to_keep: int = 1) -> int:
    """
    Limpia conversaciones más antiguas que el número de días especificado.
    
    Args:
        days_to_keep: Número de días de conversaciones a mantener (default: 1, solo hoy).
    
    Returns:
        Número de claves eliminadas.
    """
    client = get_redis_client()
    if client is None:
        return 0
    
    try:
        # Obtener todas las claves de conversación
        pattern = "conversation:*"
        keys = client.keys(pattern)
        
        if not keys:
            return 0
        
        # Calcular fecha límite
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        deleted_count = 0
        for key in keys:
            # Extraer fecha de la clave (formato: conversation:user_id:YYYY-MM-DD)
            parts = key.split(":")
            if len(parts) >= 3:
                date_str = parts[-1]
                if date_str < cutoff_str:
                    client.delete(key)
                    deleted_count += 1
        
        logger.info(f"Limpieza de conversaciones antiguas: {deleted_count} claves eliminadas")
        return deleted_count
    
    except Exception as e:
        logger.error(f"Error en limpieza de conversaciones: {e}", exc_info=True)
        return 0

