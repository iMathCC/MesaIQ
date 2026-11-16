"""Unit tests for ImportReviewsUseCase using in-memory doubles."""

from types import TracebackType
from uuid import UUID, uuid4

import pytest

from mesaiq.application.ports.unit_of_work import UnitOfWork
from mesaiq.application.use_cases.import_reviews import (
    ImportReviewsUseCase,
    RestaurantNotFoundError,
)
from mesaiq.domain.entities.import_job import ImportJob
from mesaiq.domain.entities.restaurant import Restaurant
from mesaiq.domain.entities.review import Review
from mesaiq.domain.enums import ImportJobStatus
from mesaiq.domain.exceptions import ImportJobNotFoundError
from mesaiq.infrastructure.parsers.csv_review_parser import CsvReviewParserImpl


class FakeRestaurantRepository:
    def __init__(self, restaurants: dict[UUID, Restaurant]) -> None:
        self._restaurants = restaurants

    async def get_by_id(self, restaurant_id: UUID) -> Restaurant | None:
        return self._restaurants.get(restaurant_id)


class FakeReviewRepository:
    def __init__(self, existing_reviews: set[tuple[UUID, str, str]] | None = None) -> None:
        self.existing_keys = existing_reviews or set()
        self.saved_reviews: list[Review] = []

    async def insert_many_if_not_exists(
        self,
        reviews: list[Review],
    ) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        for rev in reviews:
            key = (rev.restaurant_id, rev.source_system, rev.external_id)
            if key in self.existing_keys:
                skipped += 1
            else:
                self.existing_keys.add(key)
                self.saved_reviews.append(rev)
                inserted += 1
        return inserted, skipped


class FakeImportJobRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, ImportJob] = {}

    async def create(self, job: ImportJob) -> ImportJob:
        self.jobs[job.id] = job
        return job

    async def update(self, job: ImportJob) -> ImportJob:
        if job.id not in self.jobs:
            raise ImportJobNotFoundError(f"ImportJob {job.id} not found")
        self.jobs[job.id] = job
        return job

    async def get_by_id(self, job_id: UUID) -> ImportJob | None:
        return self.jobs.get(job_id)


class FakeUnitOfWork(UnitOfWork):
    def __init__(
        self,
        restaurants_repo: FakeRestaurantRepository,
        reviews_repo: FakeReviewRepository,
        import_jobs_repo: FakeImportJobRepository,
        fail_on_commit_after_call_count: int = 0,
    ) -> None:
        self.restaurants = restaurants_repo
        self.reviews = reviews_repo
        self.import_jobs = import_jobs_repo
        self.fail_on_commit_after_call_count = fail_on_commit_after_call_count
        self.commit_call_count = 0
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        self.commit_call_count += 1
        if (
            self.fail_on_commit_after_call_count > 0
            and self.commit_call_count >= self.fail_on_commit_after_call_count
        ):
            raise RuntimeError("Simulated DB connection drop on commit!")
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class TestImportReviewsUseCase:
    def setup_method(self) -> None:
        self.restaurant_id = uuid4()
        self.restaurant = Restaurant(id=self.restaurant_id, name="Cantina")
        self.restaurants_map = {self.restaurant_id: self.restaurant}
        self.restaurants_repo = FakeRestaurantRepository(self.restaurants_map)
        self.reviews_repo = FakeReviewRepository()
        self.jobs_repo = FakeImportJobRepository()
        self.parser = CsvReviewParserImpl()

    def make_uow_factory(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(
            self.restaurants_repo,
            self.reviews_repo,
            self.jobs_repo,
        )

    @pytest.mark.asyncio
    async def test_import_successful(self) -> None:
        csv_data = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,5,Excelente!,2026-10-12T14:30:00\n"
            b"ifood,rev-002,3,Medio.,2026-10-13T19:15:00\n"
        )
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )

        result = await use_case.execute(
            restaurant_id=self.restaurant_id,
            filename="reviews.csv",
            content=csv_data,
        )

        assert result.status == ImportJobStatus.COMPLETED
        assert result.rows_total == 2
        assert result.rows_imported == 2
        assert result.rows_skipped == 0
        assert result.rows_rejected == 0
        assert len(result.errors) == 0

        # Check job persisted in repo
        persisted_job = self.jobs_repo.jobs[result.import_job_id]
        assert persisted_job.status == ImportJobStatus.COMPLETED
        assert persisted_job.rows_imported == 2

    @pytest.mark.asyncio
    async def test_import_restaurant_not_found(self) -> None:
        unknown_id = uuid4()
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )
        with pytest.raises(RestaurantNotFoundError):
            await use_case.execute(
                restaurant_id=unknown_id,
                filename="reviews.csv",
                content=b"header\n",
            )

    @pytest.mark.asyncio
    async def test_first_invalid_row_followed_by_valid_duplicate_wins(self) -> None:
        """First row is rejected due to invalid rating. Second row with identical key is valid.

        The valid row must NOT be skipped, but imported successfully.
        """
        csv_data = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,99,Nota invalida,2026-10-12T14:30:00\n"
            b"google,rev-001,5,Nota valida,2026-10-12T14:35:00\n"
        )
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )

        result = await use_case.execute(
            restaurant_id=self.restaurant_id,
            filename="reviews.csv",
            content=csv_data,
        )

        assert result.status == ImportJobStatus.COMPLETED
        assert result.rows_imported == 1
        assert result.rows_skipped == 0
        assert result.rows_rejected == 1
        assert result.rows_total == 2
        assert len(result.errors) == 1
        assert result.errors[0].field == "rating"

    @pytest.mark.asyncio
    async def test_first_valid_row_followed_by_valid_duplicate_is_skipped(self) -> None:
        """First row is valid and imported. Second row with identical key is skipped."""
        csv_data = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,5,Primeira valida,2026-10-12T14:30:00\n"
            b"google,rev-001,4,Segunda valida duplicada,2026-10-12T15:00:00\n"
        )
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )

        result = await use_case.execute(
            restaurant_id=self.restaurant_id,
            filename="reviews.csv",
            content=csv_data,
        )

        assert result.status == ImportJobStatus.COMPLETED
        assert result.rows_imported == 1
        assert result.rows_skipped == 1
        assert result.rows_rejected == 0
        assert result.rows_total == 2

    @pytest.mark.asyncio
    async def test_import_with_invalid_rows_and_intra_file_duplicates(self) -> None:
        csv_data = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,5,Primeira vez,2026-10-12T14:30:00\n"
            b"google,rev-001,4,Duplicada no mesmo arquivo,2026-10-12T15:00:00\n"
            b"google,rev-002,invalid_rating,Conteudo,2026-10-12T16:00:00\n"
            b"ifood,rev-003,5,,2026-10-12T17:00:00\n"  # missing content
            b"ifood,rev-004,1,Data ruim,not-a-date\n"
        )
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )

        result = await use_case.execute(
            restaurant_id=self.restaurant_id,
            filename="reviews.csv",
            content=csv_data,
        )

        assert result.status == ImportJobStatus.COMPLETED
        assert result.rows_imported == 1  # rev-001
        assert result.rows_skipped == 1  # second rev-001
        assert result.rows_rejected == 3  # invalid_rating, missing content, bad date
        assert result.rows_total == 5
        assert len(result.errors) == 3
        assert result.errors[0].field == "rating"
        assert result.errors[1].field == "content"
        assert result.errors[2].field == "reviewed_at"

    @pytest.mark.asyncio
    async def test_import_skips_database_duplicates(self) -> None:
        # Pre-seed review in repo
        existing_key = (self.restaurant_id, "google", "rev-already-there")
        self.reviews_repo.existing_keys.add(existing_key)

        csv_data = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-already-there,5,Ja no banco,2026-10-12T14:30:00\n"
            b"google,rev-new,4,Nova avaliacao,2026-10-12T15:00:00\n"
        )
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )

        result = await use_case.execute(
            restaurant_id=self.restaurant_id,
            filename="reviews.csv",
            content=csv_data,
        )

        assert result.status == ImportJobStatus.COMPLETED
        assert result.rows_imported == 1
        assert result.rows_skipped == 1
        assert result.rows_rejected == 0
        assert result.rows_total == 2

    @pytest.mark.asyncio
    async def test_import_structural_csv_error_marks_job_failed(self) -> None:
        csv_data = b"col1,col2,col3\nval1,val2,val3\n"
        use_case = ImportReviewsUseCase(
            uow_factory=self.make_uow_factory,
            parser=self.parser,
        )

        result = await use_case.execute(
            restaurant_id=self.restaurant_id,
            filename="bad_columns.csv",
            content=csv_data,
        )

        assert result.status == ImportJobStatus.FAILED
        assert result.rows_total == 0
        assert result.rows_imported == 0
        assert "Missing required columns" in (result.error_summary or "")

        job = self.jobs_repo.jobs[result.import_job_id]
        assert job.status == ImportJobStatus.FAILED
        assert "Missing required columns" in (job.error_summary or "")

    @pytest.mark.asyncio
    async def test_commit_failure_after_complete_marks_job_failed_and_propagates(self) -> None:
        """Verify ImportJob state transition and exception propagation upon commit failure.

        NOTE ON ATOMICITY SCOPE:
        This unit test validates that when a commit error occurs after complete(), the in-memory
        ImportJob transitions safely to FAILED (since complete() was invoked on a clone) and
        the exception is safely propagated to the caller.
        Full transactional atomic rollback of database rows across batches is explicitly verified
        by the PostgreSQL integration test (test_real_postgres_multi_batch_rollback_on_failure).
        """
        # Commit 1: Initial job creation in PROCESSING (succeeds)
        # Commit 2: Insertion of reviews + job completion (fails!)
        # Commit 3: Marking job as FAILED (succeeds)
        failing_uow_instance = FakeUnitOfWork(
            self.restaurants_repo,
            self.reviews_repo,
            self.jobs_repo,
            fail_on_commit_after_call_count=2,
        )

        use_case = ImportReviewsUseCase(
            uow_factory=lambda: failing_uow_instance,
            parser=self.parser,
        )

        csv_data = (
            b"source_system,external_id,rating,content,reviewed_at\n"
            b"google,rev-001,5,Excelente,2026-10-12T14:30:00\n"
        )

        with pytest.raises(RuntimeError, match="Unexpected failure during review persistence"):
            await use_case.execute(
                restaurant_id=self.restaurant_id,
                filename="reviews.csv",
                content=csv_data,
            )

        # Verify that the job was recorded as FAILED in repo
        assert len(self.jobs_repo.jobs) == 1
        persisted_job = next(iter(self.jobs_repo.jobs.values()))
        assert persisted_job.status == ImportJobStatus.FAILED
        assert "Simulated DB connection drop on commit!" in (persisted_job.error_summary or "")
        assert persisted_job.rows_total == 0
