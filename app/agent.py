"""Agente LLM con LangChain para procesar mensajes y ejecutar acciones.

Este módulo implementa el cerebro del bot usando LangChain con OpenAI Function Calling.
El agente tiene acceso a tools para interactuar con Supabase y Google Sheets.
"""

import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app import database, sheets
from app.config import get_settings
from app.memory import (
    find_recent_expense_by_description,
    get_conversation_history,
    get_last_expense,
    save_message,
    save_recent_expense,
)

logger = logging.getLogger(__name__)

# Ruta base del proyecto (directorio padre de app/)
PROJECT_ROOT = Path(__file__).parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# Contexto global para almacenar el usuario actual (thread-safe en producción)
_context = threading.local()


def _obtener_usuario_actual() -> str:
    """Obtiene el usuario actual del contexto thread-local."""
    return getattr(_context, "user", "default_user")


@lru_cache(maxsize=1)
def _cargar_prompt(nombre_archivo: str) -> str:
    """
    Carga un prompt desde un archivo Markdown en la carpeta prompts/.

    Args:
        nombre_archivo: Nombre del archivo (ej: "system_prompt.md").

    Returns:
        Contenido del prompt como string.

    Raises:
        FileNotFoundError: Si el archivo no existe.
    """
    archivo_prompt = PROMPTS_DIR / nombre_archivo

    if not archivo_prompt.exists():
        raise FileNotFoundError(
            f"Archivo de prompt no encontrado: {archivo_prompt}. "
            f"Asegúrate de que existe en la carpeta {PROMPTS_DIR}"
        )

    # Leer el archivo y limpiar el contenido
    # Removemos los encabezados Markdown (#) si existen para obtener solo el texto
    contenido = archivo_prompt.read_text(encoding="utf-8")

    # Opcional: remover el primer encabezado si es un título del documento
    # Esto permite tener títulos en el MD pero no incluirlos en el prompt
    lineas = contenido.split("\n")
    if lineas and lineas[0].startswith("#"):
        # Remover el título principal (primera línea con #)
        contenido = "\n".join(lineas[1:]).strip()

    logger.debug(f"Prompt cargado desde: {archivo_prompt}")
    return contenido


def obtener_system_prompt() -> str:
    """
    Obtiene el system prompt de Miss Toña desde el archivo Markdown.

    Returns:
        System prompt como string.
    """
    return _cargar_prompt("system_prompt.md")


# ==================== TOOLS ====================


@tool
def registrar_gasto(
    monto: float,
    item: str,
    categoria: str,
    metodo: Optional[str] = None,
    notas: Optional[str] = None,
    raw_input: Optional[str] = None,
    fecha: Optional[str] = None,
) -> str:
    """Registra un nuevo gasto en la base de datos.

    Args:
        monto: Valor del gasto (debe ser mayor a 0).
        item: Descripción del gasto (ej: "Pizza", "Taxi al aeropuerto").
        categoria: Categoría del gasto (ej: "Comida", "Transporte", "Ocio").
        metodo: Método de pago (opcional, ej: "Efectivo", "Tarjeta", "Nequi").
        notas: Notas adicionales (opcional).
        raw_input: Texto original del usuario (opcional).
        fecha: Fecha del gasto (opcional). Acepta "hoy", "ayer", "hace 3 días",
               "el viernes", o formato "YYYY-MM-DD". Si no se especifica, usa hoy.

    Returns:
        Mensaje de confirmación con los detalles del gasto registrado.
    """
    try:
        # Obtener el usuario del contexto thread-local
        user = _obtener_usuario_actual()

        # Paso 1: Registrar el gasto en Supabase (operación principal)
        gasto = database.insertar_gasto(
            user=user,
            monto=monto,
            item=item,
            categoria=categoria,
            metodo=metodo,
            notas=notas,
            raw_input=raw_input,
            fecha_gasto=fecha,
        )

        # Paso 2: Guardar el gasto en Redis para poder referenciarlo después
        # (editar/eliminar "el último gasto" sin necesidad del ID)
        save_recent_expense(
            user_id=user,
            expense_id=gasto["id"],
            expense_data={
                "monto": monto,
                "item": item,
                "categoria": categoria,
                "fecha_gasto": gasto.get("fecha_gasto"),
            },
        )

        # Obtener la fecha para mostrar en la respuesta
        fecha_gasto = gasto.get("fecha_gasto", "")
        fecha_texto = ""
        if fecha_gasto:
            from datetime import date

            fecha_obj = date.fromisoformat(fecha_gasto) if isinstance(fecha_gasto, str) else fecha_gasto
            if fecha_obj != date.today():
                # Mostrar fecha solo si no es hoy
                fecha_texto = f" (fecha: {fecha_obj.strftime('%d/%m')})"

        # Paso 3: Intentar verificar presupuesto (operación secundaria, no crítica)
        # Si falla, el gasto ya está registrado - no perdemos la operación principal
        try:
            presupuesto = sheets.obtener_presupuesto(categoria)
            if presupuesto:
                # Calcular gastos del mes para esta categoría
                gastos_mes = database.obtener_gastos(user=user, periodo="mes", categoria=categoria)
                total_gastado = sum(g.get("monto", 0) for g in gastos_mes)
                restante = presupuesto - total_gastado
                porcentaje_usado = (total_gastado / presupuesto) * 100

                return (
                    f"Gasto registrado exitosamente. ID: {gasto['id']}. "
                    f"Monto: ${monto:,.0f} en {item} ({categoria}){fecha_texto}. "
                    f"Presupuesto restante: ${restante:,.0f} ({porcentaje_usado:.1f}% usado)."
                )
        except Exception as sheets_error:
            # Google Sheets falló, pero el gasto SÍ se registró correctamente
            logger.warning(f"Error verificando presupuesto en Sheets: {sheets_error}")
            # Continúa para retornar éxito sin info de presupuesto

        # Retornar éxito sin información de presupuesto
        return (
            f"Gasto registrado exitosamente. ID: {gasto['id']}. "
            f"Monto: ${monto:,.0f} en {item} ({categoria}){fecha_texto}."
        )

    except ValueError as e:
        return f"Error de validación: {str(e)}"
    except Exception as e:
        logger.error(f"Error registrando gasto: {e}", exc_info=True)
        return f"Error al registrar el gasto: {str(e)}"


@tool
def editar_gasto(
    campo: str,
    nuevo_valor: Any,
    gasto_id: Optional[str] = None,
    descripcion: Optional[str] = None,
) -> str:
    """Edita un campo específico de un gasto existente.

    Puede identificar el gasto de tres formas:
    1. Por ID específico (gasto_id)
    2. Por descripción/item (descripcion) - busca en gastos recientes
    3. Automáticamente usa el último gasto registrado si no se especifica ninguno

    Args:
        campo: Campo a editar (monto, item, categoria, metodo, notas, fecha).
               Para fecha: acepta "ayer", "hace 3 días", "el viernes", "2025-12-20".
        nuevo_valor: Nuevo valor para el campo.
        gasto_id: ID del gasto a editar (UUID). Opcional.
        descripcion: Descripción o item del gasto para buscarlo (ej: "pizza", "taxi"). Opcional.

    Returns:
        Mensaje de confirmación con los detalles del gasto actualizado.
    """
    try:
        user = _obtener_usuario_actual()

        # Determinar el ID del gasto a editar
        if gasto_id:
            # Usar el ID proporcionado directamente
            id_a_editar = gasto_id
            contexto = f"ID: {gasto_id}"
        elif descripcion:
            # Buscar por descripción en gastos recientes
            gasto_encontrado = find_recent_expense_by_description(user, descripcion)
            if not gasto_encontrado:
                return (
                    f"No encontré un gasto reciente que coincida con '{descripcion}'. "
                    f"Intenta ser más específico o proporciona el ID del gasto."
                )
            id_a_editar = gasto_encontrado["id"]
            contexto = f"{gasto_encontrado['item']} (${gasto_encontrado['monto']:,.0f})"
        else:
            # Usar el último gasto registrado
            ultimo_gasto = get_last_expense(user)
            if not ultimo_gasto:
                return (
                    "No encontré gastos recientes para editar. "
                    "Registra un gasto primero o proporciona el ID del gasto."
                )
            id_a_editar = ultimo_gasto["id"]
            contexto = f"último gasto: {ultimo_gasto['item']} (${ultimo_gasto['monto']:,.0f})"

        # Mapear "fecha" a "fecha_gasto" para la base de datos
        campo_db = "fecha_gasto" if campo.lower() == "fecha" else campo
        campos = {campo_db: nuevo_valor}

        # Convertir monto a float si es necesario
        if campo_db == "monto":
            campos["monto"] = float(nuevo_valor)

        gasto_actualizado = database.actualizar_gasto(id_a_editar, campos)

        # Formatear el valor para mostrar
        valor_mostrar = nuevo_valor
        if campo_db == "fecha_gasto" and gasto_actualizado.get("fecha_gasto"):
            from datetime import date

            fecha_str = gasto_actualizado["fecha_gasto"]
            fecha_obj = date.fromisoformat(fecha_str) if isinstance(fecha_str, str) else fecha_str
            valor_mostrar = fecha_obj.strftime("%d/%m/%Y")

        return (
            f"Gasto actualizado exitosamente ({contexto}). "
            f"Campo '{campo}' cambiado a: {valor_mostrar}."
        )

    except ValueError as e:
        return f"Error de validación: {str(e)}"
    except Exception as e:
        logger.error(f"Error editando gasto: {e}", exc_info=True)
        return f"Error al editar el gasto: {str(e)}"


@tool
def eliminar_gasto(
    gasto_id: Optional[str] = None,
    descripcion: Optional[str] = None,
) -> str:
    """Elimina un gasto de la base de datos.

    Puede identificar el gasto de tres formas:
    1. Por ID específico (gasto_id)
    2. Por descripción/item (descripcion) - busca en gastos recientes
    3. Automáticamente usa el último gasto registrado si no se especifica ninguno

    Args:
        gasto_id: ID del gasto a eliminar (UUID). Opcional.
        descripcion: Descripción o item del gasto para buscarlo (ej: "pizza", "taxi"). Opcional.

    Returns:
        Mensaje de confirmación de eliminación.
    """
    try:
        user = _obtener_usuario_actual()

        # Determinar el ID del gasto a eliminar
        if gasto_id:
            # Usar el ID proporcionado directamente
            id_a_eliminar = gasto_id
            contexto = f"ID: {gasto_id}"
        elif descripcion:
            # Buscar por descripción en gastos recientes
            gasto_encontrado = find_recent_expense_by_description(user, descripcion)
            if not gasto_encontrado:
                return (
                    f"No encontré un gasto reciente que coincida con '{descripcion}'. "
                    f"Intenta ser más específico o proporciona el ID del gasto."
                )
            id_a_eliminar = gasto_encontrado["id"]
            contexto = f"{gasto_encontrado['item']} (${gasto_encontrado['monto']:,.0f})"
        else:
            # Usar el último gasto registrado
            ultimo_gasto = get_last_expense(user)
            if not ultimo_gasto:
                return (
                    "No encontré gastos recientes para eliminar. "
                    "Registra un gasto primero o proporciona el ID del gasto."
                )
            id_a_eliminar = ultimo_gasto["id"]
            contexto = f"último gasto: {ultimo_gasto['item']} (${ultimo_gasto['monto']:,.0f})"

        eliminado = database.eliminar_gasto(id_a_eliminar)

        if eliminado:
            return f"Gasto eliminado exitosamente ({contexto})."
        else:
            return f"No se encontró el gasto ({contexto})."

    except ValueError as e:
        return f"Error de validación: {str(e)}"
    except Exception as e:
        logger.error(f"Error eliminando gasto: {e}", exc_info=True)
        return f"Error al eliminar el gasto: {str(e)}"


@tool
def listar_gastos(
    periodo: Optional[str] = None,
    categoria: Optional[str] = None,
) -> str:
    """Lista los gastos del usuario filtrados por período y/o categoría.

    Args:
        periodo: Período de tiempo ("hoy", "ayer", "semana", "mes", "año") o None para todos.
                 También acepta "hace 3 días", "el viernes", etc.
        categoria: Filtrar por categoría específica (opcional).

    Returns:
        Resumen de los gastos encontrados con totales.
    """
    try:
        user = _obtener_usuario_actual()

        gastos = database.obtener_gastos(
            user=user,
            periodo=periodo,
            categoria=categoria,
        )

        if not gastos:
            periodo_texto = periodo if periodo else "todos los períodos"
            categoria_texto = f" en {categoria}" if categoria else ""
            return f"No se encontraron gastos para {periodo_texto}{categoria_texto}."

        # Calcular totales
        total = sum(g.get("monto", 0) for g in gastos)
        total_por_categoria: dict[str, float] = {}

        for gasto in gastos:
            cat = gasto.get("categoria", "Sin categoría")
            total_por_categoria[cat] = total_por_categoria.get(cat, 0) + gasto.get("monto", 0)

        # Construir resumen
        resumen = f"Encontré {len(gastos)} gasto(s). Total: ${total:,.0f}.\n\n"
        resumen += "Desglose por categoría:\n"

        for cat, monto in sorted(total_por_categoria.items(), key=lambda x: x[1], reverse=True):
            porcentaje = (monto / total) * 100 if total > 0 else 0
            resumen += f"- {cat}: ${monto:,.0f} ({porcentaje:.1f}%)\n"

        # Listar últimos 5 gastos (incluye quién lo registró para finanzas compartidas)
        resumen += "\nÚltimos gastos:\n"
        for gasto in gastos[:5]:
            # Usar fecha_gasto si existe, sino created_at
            fecha_raw = gasto.get("fecha_gasto") or gasto.get("created_at", "")
            fecha = fecha_raw[:10] if fecha_raw else "N/A"
            registrado_por = gasto.get("user", "")
            # Mostrar solo el primer nombre si hay espacio
            nombre_corto = registrado_por.split()[0] if registrado_por else "N/A"
            resumen += (
                f"- {fecha}: ${gasto.get('monto', 0):,.0f} "
                f"en {gasto.get('item', 'N/A')} ({gasto.get('categoria', 'N/A')}) "
                f"por {nombre_corto}\n"
            )

        return resumen

    except Exception as e:
        logger.error(f"Error listando gastos: {e}", exc_info=True)
        return f"Error al listar los gastos: {str(e)}"


@tool
def verificar_presupuesto(categoria: str) -> str:
    """Verifica el presupuesto disponible para una categoría específica.

    Lee el límite desde Google Sheets y calcula cuánto se ha gastado este mes.

    Args:
        categoria: Categoría a verificar (ej: "Comida", "Transporte").

    Returns:
        Información sobre el presupuesto, gastos y saldo restante.
    """
    try:
        user = _obtener_usuario_actual()

        # Intentar obtener presupuesto de Google Sheets
        try:
            presupuesto = sheets.obtener_presupuesto(categoria)
        except Exception as sheets_error:
            logger.warning(f"Error accediendo a Google Sheets: {sheets_error}")
            return (
                f"No pude acceder a Google Sheets para verificar el presupuesto de '{categoria}'. "
                f"Verifica que las credenciales estén configuradas correctamente."
            )

        if presupuesto is None:
            return f"No se encontró un presupuesto definido para la categoría '{categoria}'."

        # Obtener gastos del mes para esta categoría
        gastos_mes = database.obtener_gastos(user=user, periodo="mes", categoria=categoria)
        total_gastado = sum(g.get("monto", 0) for g in gastos_mes)
        restante = presupuesto - total_gastado
        porcentaje_usado = (total_gastado / presupuesto) * 100

        # Determinar estado
        if porcentaje_usado >= 100:
            estado = "⚠️ PRESUPUESTO AGOTADO"
        elif porcentaje_usado >= 85:
            estado = "⚠️ Casi agotado"
        elif porcentaje_usado >= 50:
            estado = "⚠️ Más de la mitad usado"
        else:
            estado = "✅ Bajo control"

        return (
            f"Presupuesto de {categoria}:\n"
            f"- Límite mensual: ${presupuesto:,.0f}\n"
            f"- Gastado este mes: ${total_gastado:,.0f} ({porcentaje_usado:.1f}%)\n"
            f"- Restante: ${restante:,.0f}\n"
            f"- Estado: {estado}"
        )

    except Exception as e:
        logger.error(f"Error verificando presupuesto: {e}", exc_info=True)
        return f"Error al verificar el presupuesto: {str(e)}"


@tool
def generar_reporte(periodo: str = "mes") -> str:
    """Genera un reporte de gastos por categoría para un período específico.

    Args:
        periodo: Período de tiempo ("hoy", "semana", "mes", "año"). Default: "mes".

    Returns:
        Reporte detallado con totales por categoría y análisis.
    """
    try:
        user = _obtener_usuario_actual()

        gastos = database.obtener_gastos(user=user, periodo=periodo)

        if not gastos:
            return f"No se encontraron gastos para el período '{periodo}'."

        # Calcular totales
        total = sum(g.get("monto", 0) for g in gastos)
        total_por_categoria: dict[str, float] = {}

        for gasto in gastos:
            cat = gasto.get("categoria", "Sin categoría")
            total_por_categoria[cat] = total_por_categoria.get(cat, 0) + gasto.get("monto", 0)

        # Construir reporte
        reporte = f"📊 Reporte de gastos - {periodo.capitalize()}\n\n"
        reporte += f"Total gastado: ${total:,.0f}\n"
        reporte += f"Número de transacciones: {len(gastos)}\n\n"
        reporte += "Desglose por categoría:\n"

        # Ordenar por monto descendente
        for cat, monto in sorted(total_por_categoria.items(), key=lambda x: x[1], reverse=True):
            porcentaje = (monto / total) * 100 if total > 0 else 0
            # Verificar presupuesto si está disponible
            presupuesto = sheets.obtener_presupuesto(cat)
            if presupuesto:
                porcentaje_presupuesto = (monto / presupuesto) * 100
                reporte += (
                    f"- {cat}: ${monto:,.0f} ({porcentaje:.1f}% del total, "
                    f"{porcentaje_presupuesto:.1f}% del presupuesto mensual)\n"
                )
            else:
                reporte += f"- {cat}: ${monto:,.0f} ({porcentaje:.1f}% del total)\n"

        return reporte

    except Exception as e:
        logger.error(f"Error generando reporte: {e}", exc_info=True)
        return f"Error al generar el reporte: {str(e)}"


# Lista de todas las tools disponibles
TOOLS = [
    registrar_gasto,
    editar_gasto,
    eliminar_gasto,
    listar_gastos,
    verificar_presupuesto,
    generar_reporte,
]


# ==================== AGENTE ====================


def crear_agente() -> AgentExecutor:
    """Crea y configura el agente de LangChain con las tools disponibles.

    Returns:
        AgentExecutor configurado y listo para usar.
    """
    settings = get_settings()

    # Crear el LLM
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0.7,  # Un poco de creatividad para la personalidad
        api_key=settings.openai_api_key,
    )

    # Cargar el system prompt desde el archivo
    system_prompt = obtener_system_prompt()

    # Crear el prompt template
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    # Crear el agente
    agent = create_openai_tools_agent(llm, TOOLS, prompt)

    # Crear el executor
    # verbose=False para evitar warning: "'NoneType' object has no attribute 'get'"
    # El logging se maneja por separado en el módulo
    agent_executor = AgentExecutor(
        agent=agent,
        tools=TOOLS,
        verbose=False,
        handle_parsing_errors=True,
    )

    return agent_executor


# Instancia global del agente (se inicializa en primera llamada)
_agente: Optional[AgentExecutor] = None


def obtener_agente() -> AgentExecutor:
    """Obtiene o crea la instancia del agente (singleton).

    Returns:
        AgentExecutor configurado.
    """
    global _agente

    if _agente is None:
        _agente = crear_agente()
        logger.info("Agente LangChain inicializado")

    return _agente


# Contexto global para almacenar el usuario actual (thread-safe en producción)
import threading

_context = threading.local()


def procesar_mensaje(
    texto: str,
    user: str = "default_user",
    chat_history: Optional[list] = None,
) -> str:
    """
    Procesa un mensaje del usuario usando el agente LLM.

    Args:
        texto: Texto del mensaje del usuario.
        user: Nombre del usuario (se almacena en contexto para las tools).
        chat_history: Historial de conversación previo (opcional, se ignora si Redis está activo).

    Returns:
        Respuesta del agente con personalidad de Miss Toña.
    """
    try:
        # Almacenar el usuario en el contexto local para que las tools puedan acceder
        _context.user = user

        agente = obtener_agente()

        # Obtener historial de conversación desde Redis (si está disponible)
        # Si Redis está activo, ignoramos el chat_history pasado como parámetro
        settings = get_settings()
        if settings.redis_enabled:
            messages = get_conversation_history(user_id=user, max_messages=20)
            logger.debug(f"Historial cargado desde Redis: {len(messages)} mensajes")
        else:
            # Si Redis no está activo, usar el historial pasado como parámetro
            messages = chat_history or []

        # Crear mensaje del usuario actual
        user_message = HumanMessage(content=texto)

        # Guardar mensaje del usuario en Redis (si está disponible)
        if settings.redis_enabled:
            save_message(user, user_message)

        # Ejecutar el agente
        resultado = agente.invoke(
            {
                "input": texto,
                "chat_history": messages,
            }
        )

        respuesta = resultado.get("output", "Lo siento, no pude procesar tu mensaje.")

        # Guardar respuesta del agente en Redis (si está disponible)
        if settings.redis_enabled:
            ai_message = AIMessage(content=respuesta)
            save_message(user, ai_message)

        logger.info(f"Mensaje procesado para usuario {user}: {texto[:50]}...")

        return respuesta

    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}", exc_info=True)
        return (
            "Miau... 😿 Algo salió mal mientras procesaba tu mensaje. "
            "¿Puedes intentar de nuevo? Si el problema persiste, avísame."
        )
    finally:
        # Limpiar el contexto
        if hasattr(_context, "user"):
            delattr(_context, "user")
