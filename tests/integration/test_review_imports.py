"""Integration tests for the review import endpoint."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mesaiq.api.routes.review_imports import get_uow_factory
from mesaiq.config import Settings
from mesaiq.domain.entities.restaurant import Restaurant
from mesaiq.main import create_app
from tests.unit.test_use_case_import_reviews import (
    FakeImportJobRepository,
    FakeRestaurantRepository,
    FakeReviewRepository,
    FakeUnitOfWork,
)


@pytest.fixture
def fake_uow_env() -> tuple[
    FakeRestaurantRepository, FakeReviewRepository, FakeImportJobRepository
]:
    rest_repo = FakeRestaurantRepository({})
    rev_repo = FakeReviewRepository()
    jobs_repo = FakeImportJobRepository()
    return rest_repo, rev_repo, jobs_repo


def test_import_endpoint_successful(
    settings: Settings,
    fake_uow_env: tuple[FakeRestaurantRepository, FakeReviewRepository, FakeImportJobRepository],
) -> None:
    rest_repo, rev_repo, jobs_repo = fake_uow_env
    rest_id = uuid4()
    rest_repo._restaurants[rest_id] = Restaurant(id=rest_id, name="Pizzaria Teste")

    app = create_app(settings)

    def uow_override() -> FakeUnitOfWork:
        return FakeUnitOfWork(rest_repo, rev_repo, jobs_repo)

    app.dependency_overrides[get_uow_factory] = lambda: uow_override

    csv_content = (
        b"source_system,external_id,rating,content,reviewed_at\n"
        b"google,rev-101,5,Pizza excelente!,2026-10-12T14:30:00\n"
        b"ifood,rev-102,4,Chegou rapido,2026-10-12T15:00:00\n"
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/restaurants/{rest_id}/reviews/imports",
            files={"file": ("reviews.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["rows_total"] == 2
    assert data["rows_imported"] == 2
    assert data["rows_skipped"] == 0
    assert data["rows_rejected"] == 0


def test_import_endpoint_restaurant_not_found(
    settings: Settings,
    fake_uow_env: tuple[FakeRestaurantRepository, FakeReviewRepository, FakeImportJobRepository],
) -> None:
    rest_repo, rev_repo, jobs_repo = fake_uow_env
    app = create_app(settings)

    def uow_override() -> FakeUnitOfWork:
        return FakeUnitOfWork(rest_repo, rev_repo, jobs_repo)

    app.dependency_overrides[get_uow_factory] = lambda: uow_override

    missing_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/restaurants/{missing_id}/reviews/imports",
            files={"file": ("reviews.csv", b"header\n", "text/csv")},
        )

    assert response.status_code == 404
    assert f"'{missing_id}' was not found" in response.json()["detail"]


def test_import_endpoint_invalid_file_extension(settings: Settings) -> None:
    app = create_app(settings)
    rest_id = uuid4()

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/restaurants/{rest_id}/reviews/imports",
            files={"file": ("reviews.txt", b"some text", "text/plain")},
        )

    assert response.status_code == 422
    assert "File must have a .csv extension" in response.json()["detail"]


def test_import_endpoint_file_size_exceeded(settings: Settings) -> None:
    # Set limit to 100 bytes for test
    app_settings = settings.model_copy(update={"max_upload_size_bytes": 100})
    app = create_app(app_settings)
    rest_id = uuid4()

    large_content = b"a" * 200

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/restaurants/{rest_id}/reviews/imports",
            files={"file": ("reviews.csv", large_content, "text/csv")},
        )

    assert response.status_code == 413
    assert "File exceeds maximum allowed size" in response.json()["detail"]


def test_import_endpoint_structural_failure_returns_failed_job(
    settings: Settings,
    fake_uow_env: tuple[FakeRestaurantRepository, FakeReviewRepository, FakeImportJobRepository],
) -> None:
    rest_repo, rev_repo, jobs_repo = fake_uow_env
    rest_id = uuid4()
    rest_repo._restaurants[rest_id] = Restaurant(id=rest_id, name="Pizzaria Teste")

    app = create_app(settings)

    def uow_override() -> FakeUnitOfWork:
        return FakeUnitOfWork(rest_repo, rev_repo, jobs_repo)

    app.dependency_overrides[get_uow_factory] = lambda: uow_override

    bad_csv = b"col1,col2\nval1,val2\n"

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/restaurants/{rest_id}/reviews/imports",
            files={"file": ("reviews.csv", bad_csv, "text/csv")},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "FAILED"
    assert data["rows_total"] == 0
    assert "Missing required columns" in data["error_summary"]
