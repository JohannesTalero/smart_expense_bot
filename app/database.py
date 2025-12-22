"""Cliente de Supabase para operaciones CRUD de gastos."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID

from supabase import create_client, Client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cliente global de Supabase (se inicializa en get_supabase_client)
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Obtiene o crea el cliente de Supabase (singleton).
    
    Returns:
        Cliente de Supabase configurado.
    """
    global _supabase_client
    
    if _supabase_client is None:
        settings = get_settings()
        
        try:
            # Supabase 2.27+ usa la nueva API simplificada
            _supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_key,
            )
            logger.info("Cliente de Supabase inicializado")
        except Exception as e:
            logger.error(f"Error inicializando cliente de Supabase: {e}", exc_info=True)
            raise
    
    return _supabase_client


def insertar_gasto(
    user: str,
    monto: float,
    item: str,
    categoria: str,
    metodo: Optional[str] = None,
    raw_input: Optional[str] = None,
    notas: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inserta un nuevo gasto en la base de datos.
    
    Args:
        user: Nombre del usuario que agregó el gasto.
        monto: Valor de la compra (debe ser > 0).
        item: Descripción del gasto (ej: "Pizza").
        categoria: Clasificación del gasto (ej: "Comida").
        metodo: Método de pago (opcional).
        raw_input: Texto original o transcripción (opcional).
        notas: Contexto adicional opcional (opcional).
    
    Returns:
        Diccionario con los datos del gasto insertado (incluye el id generado).
    
    Raises:
        ValueError: Si el monto es inválido.
        Exception: Si hay un error al insertar en Supabase.
    """
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0")
    
    client = get_supabase_client()
    
    # Preparar datos para insertar
    data = {
        "user": user,
        "monto": monto,
        "item": item,
        "categoria": categoria,
        "created_at": datetime.utcnow().isoformat(),
    }
    
    # Agregar campos opcionales si están presentes
    if metodo:
        data["metodo"] = metodo
    if raw_input:
        data["raw_input"] = raw_input
    if notas:
        data["notas"] = notas
    
    try:
        response = client.table("gastos").insert(data).execute()
        
        if not response.data:
            raise Exception("No se recibieron datos de la inserción")
        
        gasto = response.data[0]
        logger.info(f"Gasto insertado: ID={gasto['id']}, User={user}, Monto={monto}")
        
        return gasto
    
    except Exception as e:
        logger.error(f"Error insertando gasto: {e}", exc_info=True)
        raise


def obtener_gastos(
    user: str,
    periodo: Optional[str] = None,
    categoria: Optional[str] = None,
    limite: int = 100,
) -> List[Dict[str, Any]]:
    """
    Obtiene una lista de gastos filtrados por usuario y opcionalmente por período y categoría.
    
    Args:
        user: Nombre del usuario.
        periodo: Período de tiempo ("hoy", "semana", "mes", "año") o None para todos.
        categoria: Filtrar por categoría específica (opcional).
        limite: Número máximo de resultados (default: 100).
    
    Returns:
        Lista de diccionarios con los gastos encontrados.
    """
    client = get_supabase_client()
    
    # Construir query base
    query = client.table("gastos").select("*").eq("user", user)
    
    # Aplicar filtro de período si se especifica
    if periodo:
        ahora = datetime.utcnow()
        
        if periodo.lower() == "hoy":
            inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        elif periodo.lower() == "semana":
            inicio = ahora - timedelta(days=7)
        elif periodo.lower() == "mes":
            inicio = ahora - timedelta(days=30)
        elif periodo.lower() == "año":
            inicio = ahora - timedelta(days=365)
        else:
            logger.warning(f"Período desconocido: {periodo}, ignorando filtro")
            inicio = None
        
        if inicio:
            query = query.gte("created_at", inicio.isoformat())
    
    # Aplicar filtro de categoría si se especifica
    if categoria:
        query = query.eq("categoria", categoria)
    
    # Ordenar por fecha descendente (más recientes primero) y limitar
    query = query.order("created_at", desc=True).limit(limite)
    
    try:
        response = query.execute()
        gastos = response.data or []
        
        logger.info(
            f"Gastos obtenidos: User={user}, Periodo={periodo}, "
            f"Categoria={categoria}, Total={len(gastos)}"
        )
        
        return gastos
    
    except Exception as e:
        logger.error(f"Error obteniendo gastos: {e}", exc_info=True)
        raise


def actualizar_gasto(
    gasto_id: str,
    campos: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Actualiza uno o más campos de un gasto existente.
    
    Args:
        gasto_id: ID del gasto a actualizar (UUID como string).
        campos: Diccionario con los campos a actualizar y sus nuevos valores.
                Campos válidos: monto, item, categoria, metodo, notas.
    
    Returns:
        Diccionario con los datos del gasto actualizado.
    
    Raises:
        ValueError: Si el gasto_id es inválido o si hay campos no permitidos.
        Exception: Si hay un error al actualizar en Supabase.
    """
    # Validar que el ID sea un UUID válido
    try:
        UUID(gasto_id)
    except ValueError:
        raise ValueError(f"ID de gasto inválido: {gasto_id}")
    
    # Campos permitidos para actualizar
    campos_permitidos = {"monto", "item", "categoria", "metodo", "notas"}
    
    # Validar que todos los campos sean permitidos
    campos_invalidos = set(campos.keys()) - campos_permitidos
    if campos_invalidos:
        raise ValueError(f"Campos no permitidos para actualizar: {campos_invalidos}")
    
    # Validar monto si está presente
    if "monto" in campos and campos["monto"] <= 0:
        raise ValueError("El monto debe ser mayor a 0")
    
    client = get_supabase_client()
    
    try:
        response = (
            client.table("gastos")
            .update(campos)
            .eq("id", gasto_id)
            .execute()
        )
        
        if not response.data:
            raise Exception(f"No se encontró el gasto con ID: {gasto_id}")
        
        gasto = response.data[0]
        logger.info(f"Gasto actualizado: ID={gasto_id}, Campos={list(campos.keys())}")
        
        return gasto
    
    except Exception as e:
        logger.error(f"Error actualizando gasto: {e}", exc_info=True)
        raise


def eliminar_gasto(gasto_id: str) -> bool:
    """
    Elimina un gasto de la base de datos.
    
    Args:
        gasto_id: ID del gasto a eliminar (UUID como string).
    
    Returns:
        True si se eliminó correctamente, False si no se encontró.
    
    Raises:
        ValueError: Si el gasto_id es inválido.
        Exception: Si hay un error al eliminar en Supabase.
    """
    # Validar que el ID sea un UUID válido
    try:
        UUID(gasto_id)
    except ValueError:
        raise ValueError(f"ID de gasto inválido: {gasto_id}")
    
    client = get_supabase_client()
    
    try:
        response = (
            client.table("gastos")
            .delete()
            .eq("id", gasto_id)
            .execute()
        )
        
        eliminado = len(response.data) > 0
        
        if eliminado:
            logger.info(f"Gasto eliminado: ID={gasto_id}")
        else:
            logger.warning(f"No se encontró el gasto con ID: {gasto_id}")
        
        return eliminado
    
    except Exception as e:
        logger.error(f"Error eliminando gasto: {e}", exc_info=True)
        raise


def obtener_gasto_por_id(gasto_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un gasto específico por su ID.
    
    Args:
        gasto_id: ID del gasto (UUID como string).
    
    Returns:
        Diccionario con los datos del gasto o None si no se encuentra.
    """
    # Validar que el ID sea un UUID válido
    try:
        UUID(gasto_id)
    except ValueError:
        raise ValueError(f"ID de gasto inválido: {gasto_id}")
    
    client = get_supabase_client()
    
    try:
        response = (
            client.table("gastos")
            .select("*")
            .eq("id", gasto_id)
            .execute()
        )
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        return None
    
    except Exception as e:
        logger.error(f"Error obteniendo gasto por ID: {e}", exc_info=True)
        raise

