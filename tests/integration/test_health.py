"""Integration tests for the liveness endpoint."""

from fastapi.testclient import TestClient

from mesaiq.config import Settings
from mesaiq.main import create_app


def test_liveness_returns_ok(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mesaiq"}


def test_openapi_metadata(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "MesaIQ"
    assert payload["info"]["version"] == "0.1.0"
    assert "/api/v1/health" in payload["paths"]
    assert "/api/v1/health/ready" in payload["paths"]
