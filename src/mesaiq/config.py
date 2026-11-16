"""Centralized application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from ``MESAIQ_*`` variables.

    Values are read from the process environment and, when present, from a
    local ``.env`` file. Secrets are wrapped in :class:`~pydantic.SecretStr`
    so they are not rendered in logs or error messages.
    """

    model_config = SettingsConfigDict(
        env_prefix="MESAIQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "MesaIQ"
    environment: str = "development"
    database_url: SecretStr
    log_level: str = "INFO"
    max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB limit for uploads

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Ensure the async PostgreSQL driver is used."""
        url = value.get_secret_value()
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("MESAIQ_DATABASE_URL must start with postgresql+asyncpg://")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalize the log level to the format accepted by logging."""
        normalized = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if normalized not in allowed:
            raise ValueError(f"Invalid log level: {value!r}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    # pydantic-settings fills required fields from environment variables.
    return Settings()  # type: ignore[call-arg]
