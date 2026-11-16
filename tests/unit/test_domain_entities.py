"""Unit tests for domain entities and domain rules."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from mesaiq.domain.entities.import_job import ImportJob
from mesaiq.domain.entities.restaurant import Restaurant
from mesaiq.domain.entities.review import Review
from mesaiq.domain.enums import ImportJobStatus
from mesaiq.domain.exceptions import (
    EmptyFieldError,
    InconsistentCountersError,
    InvalidImportJobStateError,
    InvalidRatingError,
)


class TestRestaurantEntity:
    def test_valid_restaurant_creation(self) -> None:
        rest = Restaurant(name="Cantina do Matheus")
        assert rest.name == "Cantina do Matheus"
        assert rest.id is not None
        assert rest.created_at is not None

    def test_restaurant_with_empty_name_raises(self) -> None:
        with pytest.raises(EmptyFieldError, match="cannot be empty"):
            Restaurant(name="")

        with pytest.raises(EmptyFieldError, match="cannot be empty"):
            Restaurant(name="   ")


class TestReviewEntity:
    def test_valid_review_creation(self) -> None:
        rest_id = uuid4()
        now = datetime.now(UTC)
        review = Review(
            restaurant_id=rest_id,
            source_system="google",
            external_id="rev-123",
            rating=5,
            content="Excelente comida!",
            reviewed_at=now,
        )
        assert review.restaurant_id == rest_id
        assert review.source_system == "google"
        assert review.external_id == "rev-123"
        assert review.rating == 5
        assert review.content == "Excelente comida!"
        assert review.reviewed_at == now
        assert review.id is not None
        assert review.imported_at is not None
        assert review.logical_key == (rest_id, "google", "rev-123")

    def test_review_rating_below_one_raises(self) -> None:
        with pytest.raises(InvalidRatingError, match="Rating must be between 1 and 5"):
            Review(
                restaurant_id=uuid4(),
                source_system="google",
                external_id="rev-123",
                rating=0,
                content="Ruim",
                reviewed_at=datetime.now(UTC),
            )

    def test_review_rating_above_five_raises(self) -> None:
        with pytest.raises(InvalidRatingError, match="Rating must be between 1 and 5"):
            Review(
                restaurant_id=uuid4(),
                source_system="google",
                external_id="rev-123",
                rating=6,
                content="Muito bom",
                reviewed_at=datetime.now(UTC),
            )

    def test_review_empty_mandatory_fields_raises(self) -> None:
        with pytest.raises(EmptyFieldError, match="source_system cannot be empty"):
            Review(
                restaurant_id=uuid4(),
                source_system="",
                external_id="rev-123",
                rating=3,
                content="OK",
                reviewed_at=datetime.now(UTC),
            )

        with pytest.raises(EmptyFieldError, match="external_id cannot be empty"):
            Review(
                restaurant_id=uuid4(),
                source_system="google",
                external_id="",
                rating=3,
                content="OK",
                reviewed_at=datetime.now(UTC),
            )

        with pytest.raises(EmptyFieldError, match="content cannot be empty"):
            Review(
                restaurant_id=uuid4(),
                source_system="google",
                external_id="rev-123",
                rating=3,
                content="   ",
                reviewed_at=datetime.now(UTC),
            )

    def test_review_naive_datetime_becomes_timezone_aware(self) -> None:
        naive = datetime(2026, 10, 15, 12, 0, 0)
        review = Review(
            restaurant_id=uuid4(),
            source_system="ifood",
            external_id="rev-456",
            rating=4,
            content="Entrega rápida",
            reviewed_at=naive,
        )
        assert review.reviewed_at.tzinfo is not None
        assert review.reviewed_at.tzinfo == UTC


class TestImportJobEntity:
    def test_default_import_job_creation(self) -> None:
        rest_id = uuid4()
        job = ImportJob(restaurant_id=rest_id)
        assert job.restaurant_id == rest_id
        assert job.status == ImportJobStatus.PENDING
        assert job.rows_total == 0
        assert job.rows_imported == 0
        assert job.rows_skipped == 0
        assert job.rows_rejected == 0
        assert job.started_at is not None
        assert job.finished_at is None

    def test_inconsistent_counters_raise(self) -> None:
        with pytest.raises(InconsistentCountersError, match="must equal"):
            ImportJob(
                restaurant_id=uuid4(),
                rows_total=10,
                rows_imported=5,
                rows_skipped=2,
                rows_rejected=1,  # 5 + 2 + 1 = 8 != 10
            )

    def test_negative_counters_raise(self) -> None:
        with pytest.raises(InconsistentCountersError, match="cannot be negative"):
            ImportJob(
                restaurant_id=uuid4(),
                rows_total=-1,
                rows_imported=-1,
                rows_skipped=0,
                rows_rejected=0,
            )

    def test_state_transitions(self) -> None:
        job = ImportJob(restaurant_id=uuid4())
        assert job.status == ImportJobStatus.PENDING

        job.start_processing()
        assert job.status == ImportJobStatus.PROCESSING

        # Cannot start processing again
        with pytest.raises(InvalidImportJobStateError, match="Cannot start processing"):
            job.start_processing()

        # Complete job with valid counters
        job.complete(rows_total=5, rows_imported=3, rows_skipped=1, rows_rejected=1)
        assert job.status == ImportJobStatus.COMPLETED
        assert job.rows_total == 5
        assert job.rows_imported == 3
        assert job.rows_skipped == 1
        assert job.rows_rejected == 1
        assert job.finished_at is not None

        # Cannot complete already completed job
        with pytest.raises(InvalidImportJobStateError, match="Cannot complete job"):
            job.complete(rows_total=5, rows_imported=5, rows_skipped=0, rows_rejected=0)

    def test_cannot_complete_pending_job_directly(self) -> None:
        job = ImportJob(restaurant_id=uuid4())
        with pytest.raises(InvalidImportJobStateError, match="must be in PROCESSING state"):
            job.complete(rows_total=0, rows_imported=0, rows_skipped=0, rows_rejected=0)

    def test_fail_from_processing_or_pending(self) -> None:
        job1 = ImportJob(restaurant_id=uuid4())
        job1.fail("Empty file")
        assert job1.status == ImportJobStatus.FAILED
        assert job1.error_summary == "Empty file"
        assert job1.finished_at is not None

        job2 = ImportJob(restaurant_id=uuid4())
        job2.start_processing()
        job2.fail("DB connection lost", rows_total=2, rows_rejected=2)
        assert job2.status == ImportJobStatus.FAILED
        assert job2.rows_total == 2
        assert job2.rows_rejected == 2
        assert job2.error_summary == "DB connection lost"

        # Cannot fail an already completed job
        job3 = ImportJob(restaurant_id=uuid4())
        job3.start_processing()
        job3.complete(rows_total=1, rows_imported=1, rows_skipped=0, rows_rejected=0)
        with pytest.raises(InvalidImportJobStateError, match="Cannot fail job already in terminal"):
            job3.fail("Some error")
