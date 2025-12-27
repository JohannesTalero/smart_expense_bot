"""Cliente de Supabase para operaciones CRUD de gastos."""

import logging
import re
import time
from datetime import date, datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
from uuid import UUID

from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cliente global de Supabase (se inicializa en get_supabase_client)
_supabase_client: Optional[Client] = None

# Configuración de reintentos
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # segundos
MAX_BACKOFF = 10.0  # segundos
BACKOFF_MULTIPLIER = 2.0

# Type variable para el decorador
T = TypeVar("T")


def _reset_supabase_client() -> None:
    """Resetea el cliente de Supabase para forzar reconexión."""
    global _supabase_client
    _supabase_client = None
    logger.info("Cliente de Supabase reseteado para reconexión")


def with_retry(
    max_retries: int = MAX_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF,
    max_backoff: float = MAX_BACKOFF,
    backoff_multiplier: float = BACKOFF_MULTIPLIER,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorador que implementa reintentos con backoff exponencial.

    Útil para operaciones de base de datos que pueden fallar temporalmente
    cuando el servidor se "despierta" después de estar inactivo.

    Args:
        max_retries: Número máximo de reintentos.
        initial_backoff: Tiempo inicial de espera entre reintentos (segundos).
        max_backoff: Tiempo máximo de espera entre reintentos (segundos).
        backoff_multiplier: Multiplicador para el backoff exponencial.

    Returns:
        Decorador que envuelve la función con lógica de reintentos.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            backoff = initial_backoff

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Detectar errores de conexión que ameritan reintento
                    is_connection_error = any(
                        keyword in error_msg
                        for keyword in [
                            "connection",
                            "timeout",
                            "network",
                            "refused",
                            "reset",
                            "broken pipe",
                            "ssl",
                            "eof",
                            "closed",
                            "unavailable",
                            "socket",
                            "connect",
                        ]
                    )

                    # Si es el último intento o no es error de conexión, propagar
                    if attempt >= max_retries or not is_connection_error:
                        logger.error(
                            f"Error en {func.__name__} después de {attempt + 1} intento(s): {e}"
                        )
                        raise

                    # Resetear cliente para forzar reconexión
                    _reset_supabase_client()

                    logger.warning(
                        f"Intento {attempt + 1}/{max_retries + 1} falló en {func.__name__}: {e}. "
                        f"Reintentando en {backoff:.1f}s..."
                    )

                    time.sleep(backoff)
                    backoff = min(backoff * backoff_multiplier, max_backoff)

            # Si llegamos aquí, todos los reintentos fallaron
            if last_exception:
                raise last_exception
            raise Exception(f"Error desconocido en {func.__name__}")

        return wrapper

    return decorator


# Mapeo de días de la semana en español
DIAS_SEMANA = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "sabado": 5,
    "domingo": 6,
}


def parsear_fecha(texto_fecha: Optional[str]) -> date:
    """
    Convierte texto de fecha relativa o absoluta a un objeto date.

    Soporta:
    - "hoy" -> fecha actual
    - "ayer" -> fecha actual - 1 día
    - "anteayer" -> fecha actual - 2 días
    - "hace X días" -> fecha actual - X días
    - "el lunes/martes/etc" -> último día de la semana mencionado
    - "YYYY-MM-DD" -> fecha específica
    - None -> fecha actual

    Args:
        texto_fecha: Texto describiendo la fecha o None.

    Returns:
        Objeto date correspondiente.
    """
    if not texto_fecha:
        return date.today()

    texto = texto_fecha.lower().strip()

    # Fecha actual
    if texto == "hoy":
        return date.today()

    # Ayer
    if texto == "ayer":
        return date.today() - timedelta(days=1)

    # Anteayer
    if texto in ("anteayer", "antes de ayer", "antier"):
        return date.today() - timedelta(days=2)

    # "hace X días"
    match_hace = re.match(r"hace\s+(\d+)\s+d[ií]as?", texto)
    if match_hace:
        dias = int(match_hace.group(1))
        return date.today() - timedelta(days=dias)

    # Día de la semana (el lunes, el martes, etc.)
    for dia_nombre, dia_num in DIAS_SEMANA.items():
        if dia_nombre in texto:
            hoy = date.today()
            dias_atras = (hoy.weekday() - dia_num) % 7
            # Si es 0, significa que es hoy, pero probablemente se refiere a la semana pasada
            if dias_atras == 0:
                dias_atras = 7
            return hoy - timedelta(days=dias_atras)

    # Intentar parsear como fecha ISO (YYYY-MM-DD)
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Intentar parsear como DD/MM/YYYY o DD-MM-YYYY
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue

    # Si no se puede parsear, devolver hoy y loguear advertencia
    logger.warning(f"No se pudo parsear la fecha '{texto_fecha}', usando fecha actual")
    return date.today()


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


@with_retry()
def insertar_gasto(
    user: str,
    monto: float,
    item: str,
    categoria: str,
    metodo: Optional[str] = None,
    raw_input: Optional[str] = None,
    notas: Optional[str] = None,
    fecha_gasto: Optional[str] = None,
) -> dict[str, Any]:
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
        fecha_gasto: Fecha del gasto en texto (ej: "ayer", "hace 3 días", "2025-12-20").
                     Si es None, usa la fecha actual.

    Returns:
        Diccionario con los datos del gasto insertado (incluye el id generado).

    Raises:
        ValueError: Si el monto es inválido.
        Exception: Si hay un error al insertar en Supabase.
    """
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0")

    client = get_supabase_client()

    # Parsear la fecha del gasto
    fecha_real = parsear_fecha(fecha_gasto)

    # Preparar datos para insertar
    data = {
        "user": user,
        "monto": monto,
        "item": item,
        "categoria": categoria,
        "created_at": datetime.utcnow().isoformat(),
        "fecha_gasto": fecha_real.isoformat(),
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
        logger.info(
            f"Gasto insertado: ID={gasto['id']}, User={user}, Monto={monto}, Fecha={fecha_real}"
        )

        return gasto

    except Exception as e:
        logger.error(f"Error insertando gasto: {e}", exc_info=True)
        raise


@with_retry()
def obtener_gastos(
    user: Optional[str] = None,
    periodo: Optional[str] = None,
    categoria: Optional[str] = None,
    limite: int = 100,
) -> list[dict[str, Any]]:
    """
    Obtiene una lista de gastos, opcionalmente filtrados por período y categoría.

    Los gastos son compartidos entre todos los usuarios autorizados,
    por lo que no se filtra por usuario (finanzas compartidas).

    Args:
        user: Nombre del usuario (ignorado, mantenido por compatibilidad).
        periodo: Período de tiempo ("hoy", "ayer", "semana", "mes", "año") o None para todos.
                 También acepta fechas relativas como "hace 3 días".
        categoria: Filtrar por categoría específica (opcional).
        limite: Número máximo de resultados (default: 100).

    Returns:
        Lista de diccionarios con los gastos encontrados.
    """
    client = get_supabase_client()

    # Construir query base - Sin filtro por usuario (finanzas compartidas)
    query = client.table("gastos").select("*")

    # Aplicar filtro de período si se especifica
    if periodo:
        hoy = date.today()
        periodo_lower = periodo.lower().strip()

        # Períodos que son un día específico
        if periodo_lower == "hoy":
            fecha_inicio = hoy
            fecha_fin = hoy
        elif periodo_lower == "ayer":
            fecha_inicio = hoy - timedelta(days=1)
            fecha_fin = fecha_inicio
        elif periodo_lower in ("anteayer", "antes de ayer", "antier"):
            fecha_inicio = hoy - timedelta(days=2)
            fecha_fin = fecha_inicio
        # Períodos que son rangos
        elif periodo_lower == "semana":
            fecha_inicio = hoy - timedelta(days=7)
            fecha_fin = hoy
        elif periodo_lower == "mes":
            fecha_inicio = hoy - timedelta(days=30)
            fecha_fin = hoy
        elif periodo_lower == "año":
            fecha_inicio = hoy - timedelta(days=365)
            fecha_fin = hoy
        else:
            # Intentar parsear como fecha específica o relativa
            try:
                fecha_parseada = parsear_fecha(periodo)
                fecha_inicio = fecha_parseada
                fecha_fin = fecha_parseada
            except Exception:
                logger.warning(f"Período desconocido: {periodo}, ignorando filtro")
                fecha_inicio = None
                fecha_fin = None

        # Aplicar filtros de fecha usando fecha_gasto
        if fecha_inicio and fecha_fin:
            if fecha_inicio == fecha_fin:
                # Día específico
                query = query.eq("fecha_gasto", fecha_inicio.isoformat())
            else:
                # Rango de fechas
                query = query.gte("fecha_gasto", fecha_inicio.isoformat())
                query = query.lte("fecha_gasto", fecha_fin.isoformat())

    # Aplicar filtro de categoría si se especifica
    if categoria:
        query = query.eq("categoria", categoria)

    # Ordenar por fecha de creación descendente (más recientes primero) y limitar
    query = query.order("created_at", desc=True).limit(limite)

    try:
        response = query.execute()
        gastos = response.data or []

        logger.info(
            f"Gastos obtenidos: Periodo={periodo}, Categoria={categoria}, Total={len(gastos)}"
        )

        return gastos

    except Exception as e:
        logger.error(f"Error obteniendo gastos: {e}", exc_info=True)
        raise


@with_retry()
def actualizar_gasto(
    gasto_id: str,
    campos: dict[str, Any],
) -> dict[str, Any]:
    """
    Actualiza uno o más campos de un gasto existente.

    Args:
        gasto_id: ID del gasto a actualizar (UUID como string).
        campos: Diccionario con los campos a actualizar y sus nuevos valores.
                Campos válidos: monto, item, categoria, metodo, notas, fecha_gasto.

    Returns:
        Diccionario con los datos del gasto actualizado.

    Raises:
        ValueError: Si el gasto_id es inválido o si hay campos no permitidos.
        Exception: Si hay un error al actualizar en Supabase.
    """
    # Validar que el ID sea un UUID válido
    try:
        UUID(gasto_id)
    except ValueError as e:
        raise ValueError(f"ID de gasto inválido: {gasto_id}") from e

    # Campos permitidos para actualizar
    campos_permitidos = {"monto", "item", "categoria", "metodo", "notas", "fecha_gasto"}

    # Validar que todos los campos sean permitidos
    campos_invalidos = set(campos.keys()) - campos_permitidos
    if campos_invalidos:
        raise ValueError(f"Campos no permitidos para actualizar: {campos_invalidos}")

    # Validar monto si está presente
    if "monto" in campos and campos["monto"] <= 0:
        raise ValueError("El monto debe ser mayor a 0")

    # Parsear fecha_gasto si está presente como texto
    if "fecha_gasto" in campos and isinstance(campos["fecha_gasto"], str):
        fecha_parseada = parsear_fecha(campos["fecha_gasto"])
        campos["fecha_gasto"] = fecha_parseada.isoformat()

    client = get_supabase_client()

    try:
        response = client.table("gastos").update(campos).eq("id", gasto_id).execute()

        if not response.data:
            raise Exception(f"No se encontró el gasto con ID: {gasto_id}")

        gasto = response.data[0]
        logger.info(f"Gasto actualizado: ID={gasto_id}, Campos={list(campos.keys())}")

        return gasto

    except Exception as e:
        logger.error(f"Error actualizando gasto: {e}", exc_info=True)
        raise


@with_retry()
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
    except ValueError as e:
        raise ValueError(f"ID de gasto inválido: {gasto_id}") from e

    client = get_supabase_client()

    try:
        response = client.table("gastos").delete().eq("id", gasto_id).execute()

        eliminado = len(response.data) > 0

        if eliminado:
            logger.info(f"Gasto eliminado: ID={gasto_id}")
        else:
            logger.warning(f"No se encontró el gasto con ID: {gasto_id}")

        return eliminado

    except Exception as e:
        logger.error(f"Error eliminando gasto: {e}", exc_info=True)
        raise


@with_retry()
def obtener_gasto_por_id(gasto_id: str) -> Optional[dict[str, Any]]:
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
    except ValueError as e:
        raise ValueError(f"ID de gasto inválido: {gasto_id}") from e

    client = get_supabase_client()

    try:
        response = client.table("gastos").select("*").eq("id", gasto_id).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]

        return None

    except Exception as e:
        logger.error(f"Error obteniendo gasto por ID: {e}", exc_info=True)
        raise
