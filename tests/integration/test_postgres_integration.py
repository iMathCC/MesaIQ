"""Integration tests executing against a real isolated PostgreSQL database (mesaiq_test)."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mesaiq.config import Settings
from mesaiq.domain.entities.import_job import ImportJob as ImportJobEntity
from mesaiq.domain.entities.review import Review as ReviewEntity
from mesaiq.domain.enums import ImportJobStatus
from mesaiq.infrastructure.database.models import ImportJob as ImportJobModel
from mesaiq.infrastructure.database.models import Restaurant as RestaurantModel
from mesaiq.infrastructure.database.models import Review as ReviewModel
from mesaiq.infrastructure.database.repositories.restaurant_repository import (
    SqlAlchemyRestaurantRepository,
)
from mesaiq.infrastructure.database.repositories.review_repository import (
    SqlAlchemyReviewRepository,
)
from mesaiq.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from mesaiq.main import create_app
from tests.database_guard import validate_test_database_url

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def db_url() -> str:
    """Validate and return the test database URL enforcing strict mesaiq_test allowlist."""
    return validate_test_database_url(os.getenv("MESAIQ_TEST_DATABASE_URL"))


@pytest.fixture
async def async_tracked_restaurants(
    db_url: str,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], list[UUID]]]:
    """Yield a per-test session factory and list to track and clean up created restaurants."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    created_ids: list[UUID] = []

    try:
        yield factory, created_ids
    finally:
        if created_ids:
            async with factory() as session:
                # Respect FKs: delete children first, then restaurants
                await session.execute(
                    delete(ReviewModel).where(ReviewModel.restaurant_id.in_(created_ids))
                )
                await session.execute(
                    delete(ImportJobModel).where(ImportJobModel.restaurant_id.in_(created_ids))
                )
                await session.execute(
                    delete(RestaurantModel).where(RestaurantModel.id.in_(created_ids))
                )
                await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_restaurant_and_review_repositories(
    async_tracked_restaurants: tuple[async_sessionmaker[AsyncSession], list[UUID]],
) -> None:
    session_factory, tracked_ids = async_tracked_restaurants
    test_rest_id = uuid4()
    tracked_ids.append(test_rest_id)

    async with session_factory() as session:
        # 1. Create a real restaurant record in DB
        rest_model = RestaurantModel(id=test_rest_id, name="Restaurante Teste Real")
        session.add(rest_model)
        await session.commit()

    async with session_factory() as session:
        rest_repo = SqlAlchemyRestaurantRepository(session)
        found = await rest_repo.get_by_id(test_rest_id)
        assert found is not None
        assert found.id == test_rest_id
        assert found.name == "Restaurante Teste Real"

        # 2. Insert reviews with repository using ON CONFLICT DO NOTHING
        rev_repo = SqlAlchemyReviewRepository(session)
        rev1 = ReviewEntity(
            restaurant_id=test_rest_id,
            source_system="google",
            external_id="real-1",
            rating=5,
            content="Excelente comida real",
            reviewed_at=datetime.now(UTC),
        )
        rev2 = ReviewEntity(
            restaurant_id=test_rest_id,
            source_system="google",
            external_id="real-2",
            rating=4,
            content="Muito bom real",
            reviewed_at=datetime.now(UTC),
        )

        inserted, skipped = await rev_repo.insert_many_if_not_exists([rev1, rev2])
        await session.commit()
        assert inserted == 2
        assert skipped == 0

        # Try to re-insert rev1 (conflict expected -> skipped)
        rev1_dup = ReviewEntity(
            restaurant_id=test_rest_id,
            source_system="google",
            external_id="real-1",
            rating=1,  # different rating, must not overwrite
            content="Tentativa de overwrite",
            reviewed_at=datetime.now(UTC),
        )
        rev3 = ReviewEntity(
            restaurant_id=test_rest_id,
            source_system="google",
            external_id="real-3",
            rating=3,
            content="Terceira avaliacao",
            reviewed_at=datetime.now(UTC),
        )

        inserted_2, skipped_2 = await rev_repo.insert_many_if_not_exists([rev1_dup, rev3])
        await session.commit()
        assert inserted_2 == 1  # only rev3
        assert skipped_2 == 1  # rev1_dup was skipped

        # Verify rev1 was NOT overwritten in the database
        stmt = select(ReviewModel).where(
            ReviewModel.restaurant_id == test_rest_id,
            ReviewModel.external_id == "real-1",
        )
        result = await session.execute(stmt)
        saved_rev1 = result.scalar_one()
        assert saved_rev1.rating == 5
        assert saved_rev1.content == "Excelente comida real"


@pytest.mark.asyncio
async def test_real_postgres_multi_batch_rollback_on_failure(
    async_tracked_restaurants: tuple[async_sessionmaker[AsyncSession], list[UUID]],
) -> None:
    """Test that a failure injected during an intermediate batch causes a full rollback.

    Workflow:
    1. Create an isolated restaurant.
    2. Create an ImportJob in PROCESSING and commit its initial persistence.
    3. Configure repository batch size to 2 (with 6 reviews -> 3 batches).
    4. First batch inserts successfully in PostgreSQL.
    5. Second batch execution raises an error.
    6. Error propagates through UnitOfWork to trigger its transaction rollback.
    7. In a new session, verify 0 reviews were persisted from this import.
    8. The ImportJob is marked as FAILED in an error handler transaction.
    9. Verify ImportJob exists, is FAILED, and counters remain consistent (all 0).
    """
    session_factory, tracked_ids = async_tracked_restaurants
    rest_id = uuid4()
    tracked_ids.append(rest_id)

    # 1. Create isolated restaurant
    async with session_factory() as session:
        session.add(RestaurantModel(id=rest_id, name="Restaurante Batch Rollback"))
        await session.commit()

    # 2. Create ImportJob in PROCESSING and commit initial persistence
    job = ImportJobEntity(restaurant_id=rest_id)
    job.start_processing()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await uow.import_jobs.create(job)
        await uow.commit()

    # 3. Prepare 6 reviews with batch_size=2 -> 3 batches
    reviews = [
        ReviewEntity(
            restaurant_id=rest_id,
            source_system="google",
            external_id=f"batch-rollback-{i}",
            rating=5,
            content=f"Conteudo {i}",
            reviewed_at=datetime.now(UTC),
        )
        for i in range(6)
    ]

    # 4 & 5 & 6. Injected failure on batch 2 escaping the context
    uow = SqlAlchemyUnitOfWork(session_factory)
    batch_count = 0

    with pytest.raises(RuntimeError, match="Injected database connection failure on batch 2!"):
        async with uow:
            uow.reviews._batch_size = 2  # type: ignore[attr-defined]
            real_execute = uow._session.execute  # type: ignore[union-attr]

            async def injected_execute(statement, *args, **kwargs):  # type: ignore[no-untyped-def]
                nonlocal batch_count
                stmt_str = str(statement)
                if "INSERT INTO reviews" in stmt_str:
                    batch_count += 1
                    if batch_count == 2:
                        raise RuntimeError("Injected database connection failure on batch 2!")
                return await real_execute(statement, *args, **kwargs)

            uow._session.execute = injected_execute  # type: ignore[union-attr]

            # 7. Batch 1 succeeds; Batch 2 raises, escaping the context and
            # triggering automatic rollback in SqlAlchemyUnitOfWork.__aexit__
            await uow.reviews.insert_many_if_not_exists(reviews)
            await uow.commit()

    # 8. Mark job as FAILED in separate transaction (simulating use case error handler)
    async with SqlAlchemyUnitOfWork(session_factory) as fail_uow:
        job.fail(error_summary="Failed during batch 2")
        await fail_uow.import_jobs.update(job)
        await fail_uow.commit()

    # 9, 10, 11. Verify in fresh session: 0 reviews persisted and job is FAILED
    async with session_factory() as session:
        stmt = select(ReviewModel).where(ReviewModel.restaurant_id == rest_id)
        result = await session.execute(stmt)
        persisted_reviews = result.scalars().all()
        assert len(persisted_reviews) == 0  # FULL ROLLBACK confirmed: batch 1 was undone!

        # Check job status in DB
        job_stmt = select(ImportJobModel).where(ImportJobModel.id == job.id)
        job_result = await session.execute(job_stmt)
        db_job = job_result.scalar_one()
        assert db_job.status == "FAILED"
        assert db_job.rows_total == 0
        assert db_job.rows_imported == 0
        assert db_job.rows_skipped == 0
        assert db_job.rows_rejected == 0
        assert "Failed during batch 2" in (db_job.error_summary or "")


@pytest.mark.asyncio
async def test_real_postgres_import_job_lifecycle(
    async_tracked_restaurants: tuple[async_sessionmaker[AsyncSession], list[UUID]],
) -> None:
    session_factory, tracked_ids = async_tracked_restaurants
    rest_id = uuid4()
    tracked_ids.append(rest_id)

    async with session_factory() as session:
        session.add(RestaurantModel(id=rest_id, name="Restaurante Jobs"))
        await session.commit()

    uow = SqlAlchemyUnitOfWork(session_factory)
    async with uow:
        job = ImportJobEntity(restaurant_id=rest_id)
        job.start_processing()
        await uow.import_jobs.create(job)
        await uow.commit()

        # Check in DB
        fetched = await uow.import_jobs.get_by_id(job.id)
        assert fetched is not None
        assert fetched.status == ImportJobStatus.PROCESSING

        # Complete job
        job.complete(rows_total=3, rows_imported=2, rows_skipped=1, rows_rejected=0)
        await uow.import_jobs.update(job)
        await uow.commit()

        fetched_completed = await uow.import_jobs.get_by_id(job.id)
        assert fetched_completed is not None
        assert fetched_completed.status == ImportJobStatus.COMPLETED
        assert fetched_completed.rows_imported == 2


@pytest.mark.asyncio
async def test_real_postgres_api_upload_flow(
    async_tracked_restaurants: tuple[async_sessionmaker[AsyncSession], list[UUID]],
    db_url: str,
) -> None:
    session_factory, tracked_ids = async_tracked_restaurants
    rest_id = uuid4()
    tracked_ids.append(rest_id)

    async with session_factory() as session:
        session.add(RestaurantModel(id=rest_id, name="Restaurante Upload Real"))
        await session.commit()

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=SecretStr(db_url),
        environment="test",
        log_level="DEBUG",
    )

    app = create_app(settings)

    csv_data = (
        b"source_system,external_id,rating,content,reviewed_at\n"
        b"google,real-e2e-1,5,Tudo perfeito!,2026-10-15T12:00:00\n"
        b"google,real-e2e-1,4,Duplicada no arquivo,2026-10-15T13:00:00\n"
        b"ifood,real-e2e-2,1,Chegou revirado,2026-10-15T14:00:00\n"
        b"ifood,real-e2e-3,invalid,Rating ruim,2026-10-15T15:00:00\n"
    )

    with TestClient(app) as client:
        # First upload: 2 imported, 1 skipped (intra-file duplicate), 1 rejected (invalid rating)
        response = client.post(
            f"/api/v1/restaurants/{rest_id}/reviews/imports",
            files={"file": ("real_test.csv", csv_data, "text/csv")},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "COMPLETED"
        assert body["rows_total"] == 4
        assert body["rows_imported"] == 2  # real-e2e-1 and real-e2e-2
        assert body["rows_skipped"] == 1  # duplicate real-e2e-1
        assert body["rows_rejected"] == 1  # invalid rating
        assert len(body["errors"]) == 1
        assert body["errors"][0]["field"] == "rating"

        # Second upload with the exact same file:
        # Previously imported reviews are now in the DB and must be SKIPPED, NOT overwritten
        response_reupload = client.post(
            f"/api/v1/restaurants/{rest_id}/reviews/imports",
            files={"file": ("real_test.csv", csv_data, "text/csv")},
        )

        assert response_reupload.status_code == 201
        body_reupload = response_reupload.json()
        assert body_reupload["status"] == "COMPLETED"
        assert body_reupload["rows_total"] == 4
        assert body_reupload["rows_imported"] == 0  # 0 new reviews
        assert body_reupload["rows_skipped"] == 3  # 1 intra-file + 2 existing in DB
        assert body_reupload["rows_rejected"] == 1  # invalid rating
