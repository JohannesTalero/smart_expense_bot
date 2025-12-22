"""Configuración de la aplicación usando Pydantic Settings."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde variables de entorno."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(..., description="Token del bot de Telegram")
    telegram_webhook_secret: Optional[str] = Field(
        None, description="Secreto opcional para validar webhooks"
    )
    telegram_allowed_user_ids: str = Field(
        ..., description="IDs de usuarios autorizados separados por coma"
    )

    # OpenAI
    openai_api_key: str = Field(..., description="API Key de OpenAI")
    openai_model: str = Field(
        default="gpt-4o-mini", description="Modelo de OpenAI a usar"
    )

    # Supabase
    supabase_url: str = Field(..., description="URL del proyecto Supabase")
    supabase_key: str = Field(..., description="Anon key de Supabase")
    supabase_service_key: Optional[str] = Field(
        None, description="Service key de Supabase (opcional)"
    )

    # Google Sheets
    google_sheets_credentials_path: str = Field(
        default="./credentials.json",
        description="Ruta al archivo de credenciales de Google Sheets",
    )
    google_sheets_spreadsheet_id: str = Field(
        ..., description="ID de la hoja de cálculo de Google Sheets"
    )
    google_sheets_worksheet_name: str = Field(
        default="Presupuestos", description="Nombre de la hoja de trabajo"
    )

    # Redis (Opcional pero recomendado para memoria conversacional)
    redis_url: Optional[str] = Field(
        default="redis://localhost:6379", description="URL de Redis (ej: redis://localhost:6379)"
    )
    redis_enabled: bool = Field(
        default=True, description="Habilitar Redis para memoria conversacional (recomendado)"
    )

    # Application
    environment: str = Field(default="development", description="Entorno de ejecución")
    log_level: str = Field(default="INFO", description="Nivel de logging")
    rate_limit_per_minute: int = Field(
        default=30, description="Límite de mensajes por minuto por usuario"
    )
    high_expense_threshold: int = Field(
        default=500000,
        description="Umbral para pedir confirmación en gastos altos (COP)",
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Host del servidor")
    port: int = Field(default=8000, description="Puerto del servidor")
    
    # Telegram Polling (para desarrollo local)
    use_polling: bool = Field(
        default=False,
        description="Usar polling en lugar de webhooks (útil para desarrollo local)"
    )
    polling_interval: float = Field(
        default=1.0,
        description="Intervalo en segundos entre consultas de polling"
    )

    @property
    def allowed_user_ids_list(self) -> List[int]:
        """Convierte la cadena de IDs permitidos en una lista de enteros."""
        return [
            int(user_id.strip())
            for user_id in self.telegram_allowed_user_ids.split(",")
            if user_id.strip()
        ]

    def is_user_allowed(self, user_id: int) -> bool:
        """Verifica si un usuario está autorizado."""
        return user_id in self.allowed_user_ids_list


@lru_cache()
def get_settings() -> Settings:
    """Obtiene la configuración de la aplicación (cached)."""
    return Settings()

