"""Tests de integración para servicios externos.

Estos tests verifican que las conexiones a Supabase, Redis y Google Sheets
funcionen correctamente con credenciales reales.

NOTA: Estos tests requieren configuración real en .env y conexión a internet.
Se recomienda ejecutarlos manualmente cuando se necesite verificar conectividad.
"""

import os
from uuid import uuid4

import pytest

# Marcar todos los tests como de integración (se pueden skipear con -m "not integration")
pytestmark = pytest.mark.integration


class TestSupabaseIntegration:
    """Tests de integración para Supabase."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Verifica que las variables de entorno estén configuradas."""
        from app.config import get_settings

        settings = get_settings()

        if not settings.supabase_url or not settings.supabase_key:
            pytest.skip("Variables de Supabase no configuradas")

        # Saltar si es una URL de prueba (común en CI)
        if "test.supabase.co" in settings.supabase_url or settings.supabase_key == "test_key":
            pytest.skip("Credenciales de Supabase son valores de prueba (normal en CI)")

    def test_conexion_supabase(self):
        """Verifica que se pueda conectar a Supabase."""
        # Limpiar cliente existente para forzar reconexión
        import app.database as db_module
        from app.database import get_supabase_client

        db_module._supabase_client = None

        client = get_supabase_client()

        assert client is not None, "No se pudo crear el cliente de Supabase"

    def test_insertar_y_eliminar_gasto(self):
        """Verifica que se pueda insertar y eliminar un gasto en Supabase."""
        from app.database import eliminar_gasto, insertar_gasto, obtener_gasto_por_id

        # Crear un gasto de prueba
        test_user = f"test_integration_{uuid4().hex[:8]}"
        gasto = insertar_gasto(
            user=test_user,
            monto=1.0,  # Monto mínimo para prueba
            item="Test Integration",
            categoria="Test",
            notas="Este gasto es de prueba y será eliminado",
        )

        assert gasto is not None, "No se pudo insertar el gasto"
        assert "id" in gasto, "El gasto no tiene ID"
        assert gasto["monto"] == 1.0

        gasto_id = gasto["id"]

        # Verificar que el gasto existe
        gasto_recuperado = obtener_gasto_por_id(gasto_id)
        assert gasto_recuperado is not None, "No se pudo recuperar el gasto"

        # Limpiar: eliminar el gasto de prueba
        eliminado = eliminar_gasto(gasto_id)
        assert eliminado is True, "No se pudo eliminar el gasto de prueba"

        # Verificar que ya no existe
        gasto_eliminado = obtener_gasto_por_id(gasto_id)
        assert gasto_eliminado is None, "El gasto no fue eliminado correctamente"

    def test_obtener_gastos_usuario(self):
        """Verifica que se puedan obtener gastos de un usuario."""
        from app.database import obtener_gastos

        # Usar un usuario que probablemente no exista para obtener lista vacía
        gastos = obtener_gastos(user="usuario_inexistente_test_12345")

        assert isinstance(gastos, list), "obtener_gastos debe retornar una lista"


class TestRedisIntegration:
    """Tests de integración para Redis/Upstash."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Verifica que Redis esté configurado."""
        from app.config import get_settings

        settings = get_settings()

        if not settings.redis_enabled:
            pytest.skip("Redis no está habilitado")
        if not settings.redis_url:
            pytest.skip("URL de Redis no configurada")

    def test_conexion_redis(self):
        """Verifica que se pueda conectar a Redis."""
        # Limpiar cliente existente para forzar reconexión
        import app.memory as memory_module
        from app.memory import get_redis_client

        memory_module._redis_client = None

        client = get_redis_client()

        assert client is not None, "No se pudo crear el cliente de Redis"

    def test_guardar_y_recuperar_mensaje(self):
        """Verifica que se puedan guardar y recuperar mensajes en Redis."""
        from langchain_core.messages import AIMessage, HumanMessage

        from app.memory import clear_conversation_history, get_conversation_history, save_message

        test_user = f"test_integration_{uuid4().hex[:8]}"

        # Limpiar historial previo (por si acaso)
        clear_conversation_history(test_user)

        # Guardar mensajes de prueba
        msg1 = HumanMessage(content="Mensaje de prueba 1")
        msg2 = AIMessage(content="Respuesta de prueba 1")

        saved1 = save_message(test_user, msg1)
        saved2 = save_message(test_user, msg2)

        assert saved1 is True, "No se pudo guardar el primer mensaje"
        assert saved2 is True, "No se pudo guardar el segundo mensaje"

        # Recuperar historial
        history = get_conversation_history(test_user)

        assert len(history) >= 2, f"Se esperaban al menos 2 mensajes, se obtuvieron {len(history)}"

        # Limpiar
        cleared = clear_conversation_history(test_user)
        assert cleared is True, "No se pudo limpiar el historial"

        # Verificar que está vacío
        history_after = get_conversation_history(test_user)
        assert len(history_after) == 0, "El historial no se limpió correctamente"


class TestGoogleSheetsIntegration:
    """Tests de integración para Google Sheets."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Verifica que Google Sheets esté configurado."""
        from app.config import get_settings

        settings = get_settings()

        if not settings.google_sheets_spreadsheet_id:
            pytest.skip("ID de Google Sheets no configurado")

        # Verificar si el archivo de credenciales existe
        if not os.path.exists(settings.google_sheets_credentials_path):
            pytest.skip(
                f"Archivo de credenciales no encontrado: {settings.google_sheets_credentials_path}"
            )

    def test_conexion_google_sheets(self):
        """Verifica que se pueda conectar a Google Sheets."""
        from app.sheets import get_gspread_client

        try:
            client = get_gspread_client()
            assert client is not None, "No se pudo crear el cliente de Google Sheets"
        except Exception as e:
            pytest.fail(f"Error conectando a Google Sheets: {e}")

    def test_obtener_categorias(self):
        """Verifica que se puedan obtener las categorías de presupuesto."""
        from app.sheets import obtener_categorias

        try:
            categorias = obtener_categorias()
            assert isinstance(categorias, list), "obtener_categorias debe retornar una lista"
            # No verificamos contenido porque depende de la hoja real
        except Exception as e:
            pytest.fail(f"Error obteniendo categorías: {e}")

    def test_obtener_presupuesto_categoria_inexistente(self):
        """Verifica que se maneje correctamente una categoría inexistente."""
        from app.sheets import obtener_presupuesto

        try:
            presupuesto = obtener_presupuesto("CategoriaQueNoExiste12345")
            # Debe retornar None para categoría inexistente
            assert presupuesto is None, "Debería retornar None para categoría inexistente"
        except Exception as e:
            pytest.fail(f"Error manejando categoría inexistente: {e}")
