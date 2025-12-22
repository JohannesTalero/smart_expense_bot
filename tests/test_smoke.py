"""Tests de smoke para verificar conectividad a servicios externos.

Estos tests son rápidos y verifican solo que los servicios estén accesibles.
Son útiles para ejecutar antes de deployments o como health checks.

Uso:
    pytest tests/test_smoke.py -v
    pytest tests/test_smoke.py -v --tb=short  # Con tracebacks cortos
"""

import os
import sys

import pytest

# Marcar todos los tests como smoke
pytestmark = pytest.mark.smoke


class TestSupabaseSmoke:
    """Smoke tests para Supabase."""

    def test_supabase_configurado(self):
        """Verifica que las credenciales de Supabase estén configuradas."""
        from app.config import get_settings

        settings = get_settings()

        assert settings.supabase_url, "SUPABASE_URL no está configurado"
        assert settings.supabase_key, "SUPABASE_KEY no está configurado"
        assert settings.supabase_url.startswith("https://"), "SUPABASE_URL debe ser HTTPS"

    def test_supabase_conexion(self):
        """Verifica que se pueda conectar a Supabase."""
        from app.config import get_settings

        settings = get_settings()

        if not settings.supabase_url or not settings.supabase_key:
            pytest.skip("Credenciales de Supabase no configuradas")

        # Limpiar cliente para forzar reconexión
        import app.database as db_module
        from app.database import get_supabase_client

        db_module._supabase_client = None

        try:
            client = get_supabase_client()
            assert client is not None, "Cliente de Supabase es None"
            print("✅ Supabase: Conexión exitosa")
        except Exception as e:
            pytest.fail(f"❌ Supabase: Error de conexión - {e}")


class TestRedisSmoke:
    """Smoke tests para Redis/Upstash."""

    def test_redis_configurado(self):
        """Verifica que Redis esté configurado."""
        from app.config import get_settings

        settings = get_settings()

        if not settings.redis_enabled:
            pytest.skip("Redis está deshabilitado")

        assert settings.redis_url, "REDIS_URL no está configurado"
        assert "://" in settings.redis_url, "REDIS_URL debe incluir protocolo"

    def test_redis_conexion(self):
        """Verifica que se pueda conectar a Redis."""
        from app.config import get_settings

        settings = get_settings()

        if not settings.redis_enabled:
            pytest.skip("Redis está deshabilitado")

        # Limpiar cliente para forzar reconexión
        import app.memory as memory_module
        from app.memory import get_redis_client

        memory_module._redis_client = None

        try:
            client = get_redis_client()

            if client is None:
                pytest.skip("Redis no disponible (retornó None)")

            # Hacer ping para verificar conexión real
            pong = client.ping()
            assert pong is True, "Redis ping falló"
            print("✅ Redis: Conexión exitosa (ping OK)")
        except Exception as e:
            pytest.fail(f"❌ Redis: Error de conexión - {e}")


class TestGoogleSheetsSmoke:
    """Smoke tests para Google Sheets."""

    def test_google_sheets_configurado(self):
        """Verifica que Google Sheets esté configurado."""
        from app.config import get_settings

        settings = get_settings()

        assert (
            settings.google_sheets_spreadsheet_id
        ), "GOOGLE_SHEETS_SPREADSHEET_ID no está configurado"
        assert (
            settings.google_sheets_credentials_path
        ), "GOOGLE_SHEETS_CREDENTIALS_PATH no está configurado"

    def test_credenciales_archivo_existe(self):
        """Verifica que el archivo de credenciales exista."""
        from app.config import get_settings

        settings = get_settings()

        # Si hay credenciales JSON en variable de entorno, no necesitamos archivo
        if (
            settings.google_sheets_credentials_json
            and settings.google_sheets_credentials_json != "{}"
        ):
            pytest.skip("Usando credenciales desde variable de entorno, no se requiere archivo")

        path = settings.google_sheets_credentials_path

        if not os.path.exists(path):
            pytest.skip(f"Archivo de credenciales no encontrado: {path} (normal en CI)")

        print(f"✅ Archivo de credenciales existe: {path}")

    def test_credenciales_formato_correcto(self):
        """Verifica que el archivo de credenciales tenga el formato correcto."""
        import json

        from app.config import get_settings

        settings = get_settings()
        path = settings.google_sheets_credentials_path

        if not os.path.exists(path):
            pytest.skip("Archivo de credenciales no existe")

        try:
            with open(path) as f:
                creds = json.load(f)

            # Verificar campos requeridos para Service Account
            required_fields = ["type", "project_id", "private_key", "client_email", "token_uri"]
            missing = [field for field in required_fields if field not in creds]

            if missing:
                pytest.fail(
                    f"❌ Credenciales incompletas. Campos faltantes: {missing}. "
                    f"Asegúrate de usar una Service Account, no OAuth credentials."
                )

            if creds.get("type") != "service_account":
                pytest.fail(
                    f"❌ Tipo de credencial incorrecto: '{creds.get('type')}'. "
                    f"Se requiere 'service_account'."
                )

            print(f"✅ Credenciales válidas (Service Account: {creds.get('client_email', 'N/A')})")

        except json.JSONDecodeError as e:
            pytest.fail(f"❌ Archivo de credenciales no es JSON válido: {e}")

    def test_google_sheets_conexion(self):
        """Verifica que se pueda conectar a Google Sheets."""
        from app.config import get_settings

        settings = get_settings()

        if not os.path.exists(settings.google_sheets_credentials_path):
            pytest.skip("Archivo de credenciales no existe")

        # Verificar formato antes de intentar conexión
        import json

        try:
            with open(settings.google_sheets_credentials_path) as f:
                creds = json.load(f)
            if creds.get("type") != "service_account":
                pytest.skip("Credenciales no son de Service Account")
        except:
            pytest.skip("No se pudo leer archivo de credenciales")

        from app.sheets import get_gspread_client

        try:
            client = get_gspread_client()
            assert client is not None, "Cliente de Google Sheets es None"
            print("✅ Google Sheets: Conexión exitosa")
        except Exception as e:
            pytest.fail(f"❌ Google Sheets: Error de conexión - {e}")


class TestOpenAISmoke:
    """Smoke tests para OpenAI."""

    def test_openai_configurado(self):
        """Verifica que OpenAI esté configurado."""
        from app.config import get_settings

        settings = get_settings()

        assert settings.openai_api_key, "OPENAI_API_KEY no está configurado"

        # Saltar si es un valor de prueba (común en CI)
        if settings.openai_api_key in ("test_key", "test", "fake_key"):
            pytest.skip("OpenAI API key es un valor de prueba (normal en CI)")

        assert settings.openai_api_key.startswith("sk-"), "OPENAI_API_KEY debe comenzar con 'sk-'"
        print(f"✅ OpenAI API Key configurada (modelo: {settings.openai_model})")


class TestTelegramSmoke:
    """Smoke tests para Telegram."""

    def test_telegram_configurado(self):
        """Verifica que Telegram esté configurado."""
        from app.config import get_settings

        settings = get_settings()

        assert settings.telegram_bot_token, "TELEGRAM_BOT_TOKEN no está configurado"

        # Saltar si es un valor de prueba (común en CI)
        if settings.telegram_bot_token in ("test_token", "test", "fake_token"):
            pytest.skip("Telegram token es un valor de prueba (normal en CI)")

        assert ":" in settings.telegram_bot_token, "TELEGRAM_BOT_TOKEN tiene formato inválido"

        # Verificar que hay usuarios autorizados
        assert settings.telegram_allowed_user_ids, "TELEGRAM_ALLOWED_USER_IDS no está configurado"

        users = settings.allowed_user_ids_list
        assert len(users) > 0, "No hay usuarios autorizados configurados"
        print(f"✅ Telegram configurado ({len(users)} usuario(s) autorizado(s))")


def run_all_smoke_tests():
    """Ejecuta todos los smoke tests y muestra un resumen."""
    print("\n" + "=" * 60)
    print("🔍 SMOKE TESTS - Verificación de Servicios Externos")
    print("=" * 60 + "\n")

    # Ejecutar pytest programáticamente
    exit_code = pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-x",  # Parar en el primer error
        ]
    )

    print("\n" + "=" * 60)
    if exit_code == 0:
        print("✅ Todos los smoke tests pasaron")
    else:
        print("❌ Algunos smoke tests fallaron")
    print("=" * 60 + "\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(run_all_smoke_tests())
