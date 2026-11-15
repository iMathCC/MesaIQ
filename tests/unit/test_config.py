"""Unit tests for environment-driven application settings."""

import pytest
from pydantic import SecretStr, ValidationError

from mesaiq.config import Settings, get_settings


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESAIQ_APP_NAME", "MesaIQ Test")
    monkeypatch.setenv("MESAIQ_ENVIRONMENT", "testing")
    monkeypatch.setenv("MESAIQ_LOG_LEVEL", "debug")
    monkeypatch.setenv(
        "MESAIQ_DATABASE_URL",
        "postgresql+asyncpg://user:super_secret@localhost:5433/db",
    )

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "MesaIQ Test"
    assert settings.environment == "testing"
    assert settings.log_level == "DEBUG"
    assert isinstance(settings.database_url, SecretStr)
    assert settings.database_url.get_secret_value().endswith("/db")


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESAIQ_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_database_url_requires_asyncpg_driver() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            database_url=SecretStr("postgresql://mesaiq:local_password@localhost:5433/mesaiq"),
        )

    assert "local_password" not in str(exc_info.value)


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            database_url=SecretStr(
                "postgresql+asyncpg://mesaiq:local_password@localhost:5433/mesaiq"
            ),
            log_level="VERBOSE",
        )


def test_database_credentials_are_not_exposed(settings: Settings) -> None:
    assert "local_password" not in repr(settings)
    assert "local_password" not in str(settings.database_url)
    assert "local_password" not in settings.model_dump().__repr__()
    assert "local_password" in settings.database_url.get_secret_value()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MESAIQ_DATABASE_URL",
        "postgresql+asyncpg://mesaiq:local_password@localhost:5433/mesaiq",
    )

    first = get_settings()
    second = get_settings()

    assert first is second
