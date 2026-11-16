"""Integration tests for the readiness endpoint and database connectivity."""

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from mesaiq.config import Settings
from mesaiq.infrastructure.database.session import get_db_session
from mesaiq.main import create_app
from tests.database_guard import validate_test_database_url


class HealthySession:
    async def execute(self, statement: Any) -> None:
        return None


class FailingSession:
    async def execute(self, statement: Any) -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("connection refused"))


async def healthy_session() -> AsyncIterator[HealthySession]:
    yield HealthySession()


async def failing_session() -> AsyncIterator[FailingSession]:
    yield FailingSession()


def test_readiness_returns_ok_when_database_is_available(settings: Settings) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_db_session] = healthy_session

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "mesaiq", "database": "ok"}


def test_readiness_returns_503_when_database_fails(settings: Settings) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_db_session] = failing_session

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "local_password" not in response.text
    assert "connection refused" not in response.text


@pytest.mark.integration
def test_readiness_against_real_database() -> None:
    database_url = validate_test_database_url(os.getenv("MESAIQ_TEST_DATABASE_URL"))

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=SecretStr(database_url),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "mesaiq", "database": "ok"}
