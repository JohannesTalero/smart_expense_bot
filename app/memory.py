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


# ==================== GASTOS RECIENTES ====================

def _get_recent_expenses_key(user_id: str) -> str:
    """
    Genera la clave Redis para los gastos recientes de un usuario.
    
    Args:
        user_id: ID del usuario.
    
    Returns:
        Clave Redis (ej: "recent_expenses:user_123").
    """
    return f"recent_expenses:{user_id}"


def save_recent_expense(user_id: str, expense_id: str, expense_data: Dict[str, Any]) -> bool:
    """
    Guarda un gasto en la lista de gastos recientes del usuario.
    
    El gasto se agrega al principio de la lista (LPUSH), manteniendo los más
    recientes primero. Se limita a los últimos 10 gastos.
    
    Args:
        user_id: ID del usuario.
        expense_id: ID del gasto (UUID de Supabase).
        expense_data: Diccionario con datos básicos del gasto (monto, item, categoria).
    
    Returns:
        True si se guardó correctamente, False en caso contrario.
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        key = _get_recent_expenses_key(user_id)
        
        # Preparar datos a guardar
        data = {
            "id": expense_id,
            "monto": expense_data.get("monto"),
            "item": expense_data.get("item"),
            "categoria": expense_data.get("categoria"),
            "timestamp": datetime.now().isoformat(),
        }
        
        # Agregar al principio de la lista (más reciente primero)
        client.lpush(key, json.dumps(data))
        
        # Mantener solo los últimos 10 gastos
        client.ltrim(key, 0, 9)
        
        # TTL de 25 horas (igual que conversaciones)
        client.expire(key, 25 * 60 * 60)
        
        logger.debug(f"Gasto reciente guardado: {expense_id} para usuario {user_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error guardando gasto reciente en Redis: {e}", exc_info=True)
        return False


def get_recent_expenses(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Obtiene los últimos gastos registrados por el usuario.
    
    Args:
        user_id: ID del usuario.
        limit: Número máximo de gastos a retornar (default: 5).
    
    Returns:
        Lista de diccionarios con los gastos recientes (más reciente primero).
        Cada diccionario tiene: id, monto, item, categoria, timestamp.
    """
    client = get_redis_client()
    if client is None:
        return []
    
    try:
        key = _get_recent_expenses_key(user_id)
        
        # Obtener los primeros N gastos (ya están ordenados por más reciente)
        expenses_json = client.lrange(key, 0, limit - 1)
        
        if not expenses_json:
            return []
        
        expenses = []
        for exp_json in expenses_json:
            try:
                expense = json.loads(exp_json)
                expenses.append(expense)
            except Exception as e:
                logger.warning(f"Error parseando gasto reciente: {e}")
                continue
        
        return expenses
    
    except Exception as e:
        logger.error(f"Error obteniendo gastos recientes de Redis: {e}", exc_info=True)
        return []


def get_last_expense(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el último gasto registrado por el usuario.
    
    Args:
        user_id: ID del usuario.
    
    Returns:
        Diccionario con los datos del último gasto o None si no hay gastos.
    """
    expenses = get_recent_expenses(user_id, limit=1)
    return expenses[0] if expenses else None


def find_recent_expense_by_description(user_id: str, search_term: str) -> Optional[Dict[str, Any]]:
    """
    Busca un gasto reciente por descripción (item) o categoría.
    
    Args:
        user_id: ID del usuario.
        search_term: Término de búsqueda (ej: "pizza", "comida").
    
    Returns:
        Diccionario con el gasto encontrado o None si no hay coincidencias.
    """
    expenses = get_recent_expenses(user_id, limit=10)
    
    if not expenses:
        return None
    
    search_lower = search_term.lower()
    
    for expense in expenses:
        item = expense.get("item", "").lower()
        categoria = expense.get("categoria", "").lower()
        
        if search_lower in item or search_lower in categoria:
            return expense
    
    return None


def clear_recent_expenses(user_id: str) -> bool:
    """
    Limpia la lista de gastos recientes del usuario.
    
    Args:
        user_id: ID del usuario.
    
    Returns:
        True si se limpió correctamente, False en caso contrario.
    """
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        key = _get_recent_expenses_key(user_id)
        deleted = client.delete(key)
        logger.info(f"Gastos recientes limpiados para usuario {user_id}")
        return deleted > 0
    
    except Exception as e:
        logger.error(f"Error limpiando gastos recientes de Redis: {e}", exc_info=True)
        return False
