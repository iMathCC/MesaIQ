"""Unit tests for repository adapters with mock sessions."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mesaiq.domain.entities.import_job import ImportJob
from mesaiq.domain.entities.review import Review
from mesaiq.domain.exceptions import ImportJobNotFoundError
from mesaiq.infrastructure.database.repositories.import_job_repository import (
    SqlAlchemyImportJobRepository,
)
from mesaiq.infrastructure.database.repositories.review_repository import (
    SqlAlchemyReviewRepository,
)


@pytest.mark.asyncio
async def test_import_job_repository_update_non_existent_raises() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    repo = SqlAlchemyImportJobRepository(session)
    job = ImportJob(restaurant_id=uuid4())

    with pytest.raises(ImportJobNotFoundError, match="not found"):
        await repo.update(job)


@pytest.mark.asyncio
async def test_review_repository_batch_insertion() -> None:
    session = AsyncMock()
    mock_result_batch1 = MagicMock()
    mock_result_batch1.scalars.return_value.all.return_value = [uuid4(), uuid4()]
    mock_result_batch2 = MagicMock()
    mock_result_batch2.scalars.return_value.all.return_value = [uuid4(), uuid4()]
    mock_result_batch3 = MagicMock()
    mock_result_batch3.scalars.return_value.all.return_value = [uuid4()]

    session.execute.side_effect = [mock_result_batch1, mock_result_batch2, mock_result_batch3]

    # batch_size=2 with 5 items -> 3 batches (2, 2, 1 items)
    repo = SqlAlchemyReviewRepository(session, batch_size=2)
    rest_id = uuid4()

    from datetime import UTC, datetime

    reviews = [
        Review(
            restaurant_id=rest_id,
            source_system="google",
            external_id=f"rev-{i}",
            rating=5,
            content="Texto",
            reviewed_at=datetime.now(UTC),
        )
        for i in range(5)
    ]

    inserted, skipped = await repo.insert_many_if_not_exists(reviews)

    # 3 execute calls for 3 batches
    assert session.execute.call_count == 3
    assert inserted == 5
    assert skipped == 0
