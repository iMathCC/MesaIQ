"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from mesaiq.config import Settings, get_settings

TEST_DATABASE_URL = "postgresql+asyncpg://mesaiq:local_password@localhost:5433/mesaiq"


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Avoid leaking cached settings between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Return deterministic application settings for tests."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="test",
        database_url=SecretStr(TEST_DATABASE_URL),
        log_level="DEBUG",
    )
