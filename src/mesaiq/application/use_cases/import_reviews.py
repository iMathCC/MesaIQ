"""ImportReviewsUseCase orchestrates the validation, ingestion and auditing of CSV reviews."""

import copy
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from mesaiq.application.dtos.import_reviews import (
    ImportReviewsResult,
    RowErrorDetail,
)
from mesaiq.application.ports.csv_parser import CsvReviewParser
from mesaiq.application.ports.unit_of_work import UnitOfWork
from mesaiq.domain.entities.import_job import ImportJob
from mesaiq.domain.entities.review import Review
from mesaiq.domain.enums import ImportJobStatus
from mesaiq.domain.exceptions import (
    DomainException,
    EmptyFieldError,
    InvalidRatingError,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ERROR_DETAILS = 50


class RestaurantNotFoundError(Exception):
    """Raised when the target restaurant does not exist."""

    def __init__(self, restaurant_id: UUID) -> None:
        super().__init__(f"Restaurant with ID {restaurant_id} not found")
        self.restaurant_id = restaurant_id


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 date/time string and ensure timezone-awareness.

    If naive, assumes UTC.
    Raises ValueError on invalid format.
    """
    clean_val = value.strip()
    if not clean_val:
        raise ValueError("reviewed_at is empty")

    dt = datetime.fromisoformat(clean_val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class ImportReviewsUseCase:
    """Orchestrates CSV review ingestion with auditing and deduplication."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        parser: CsvReviewParser,
        max_error_details: int = DEFAULT_MAX_ERROR_DETAILS,
    ) -> None:
        self._uow_factory = uow_factory
        self._parser = parser
        self._max_error_details = max_error_details

    async def execute(
        self,
        *,
        restaurant_id: UUID,
        filename: str,
        content: bytes,
    ) -> ImportReviewsResult:
        """Execute the review import process.

        Flow:
        1. Verify restaurant existence.
        2. Create and persist ImportJob in PROCESSING state.
        3. Parse the CSV bytes structurally.
        4. Validate records, track file duplicates and rejected rows.
        5. Persist valid reviews using ON CONFLICT DO NOTHING.
        6. Complete clone of ImportJob; commit transaction before mutating original state.
        7. Return structured result.
        """
        # Step 1: Verify restaurant exists
        async with self._uow_factory() as uow:
            restaurant = await uow.restaurants.get_by_id(restaurant_id)
            if restaurant is None:
                raise RestaurantNotFoundError(restaurant_id)

        # Step 2: Create and persist ImportJob in PROCESSING state in initial transaction
        job = ImportJob(restaurant_id=restaurant_id)
        job.start_processing()

        async with self._uow_factory() as uow:
            await uow.import_jobs.create(job)
            await uow.commit()

        # Step 3: Parse CSV
        try:
            raw_rows = self._parser.parse(content)
        except ValueError as exc:
            logger.warning(
                "Structural failure parsing CSV %s for job %s: %s",
                filename,
                job.id,
                exc,
            )
            error_msg = f"Structural error in CSV file: {exc}"
            job.fail(error_summary=error_msg)
            async with self._uow_factory() as uow:
                await uow.import_jobs.update(job)
                await uow.commit()

            return ImportReviewsResult(
                import_job_id=job.id,
                status=ImportJobStatus.FAILED,
                rows_total=0,
                rows_imported=0,
                rows_skipped=0,
                rows_rejected=0,
                errors=[],
                error_summary=error_msg,
            )

        # Step 4: Validate rows, identify intra-file duplicates
        valid_reviews: list[Review] = []
        seen_keys_in_file: set[tuple[str, str]] = set()
        file_skipped_count = 0
        rejected_errors: list[RowErrorDetail] = []

        for raw_row in raw_rows:
            data = raw_row.data
            line_num = raw_row.line_number

            # Parse fields
            source_system = data.get("source_system", "").strip()
            external_id = data.get("external_id", "").strip()
            raw_rating = data.get("rating", "").strip()
            content_text = data.get("content", "").strip()
            raw_reviewed_at = data.get("reviewed_at", "").strip()

            # Field presence
            if not source_system:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field="source_system",
                        reason="source_system cannot be empty",
                    )
                )
                continue

            if not external_id:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field="external_id",
                        reason="external_id cannot be empty",
                    )
                )
                continue

            if not content_text:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field="content",
                        reason="content cannot be empty",
                    )
                )
                continue

            # Rating parsing
            try:
                rating = int(raw_rating)
            except (ValueError, TypeError):
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field="rating",
                        reason=f"rating must be an integer, got {raw_rating!r}",
                    )
                )
                continue

            # Date parsing
            try:
                reviewed_at = parse_iso_datetime(raw_reviewed_at)
            except ValueError as exc:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field="reviewed_at",
                        reason=f"reviewed_at must be valid ISO 8601 date: {exc}",
                    )
                )
                continue

            # Domain entity validation
            try:
                review = Review(
                    restaurant_id=restaurant_id,
                    source_system=source_system,
                    external_id=external_id,
                    rating=rating,
                    content=content_text,
                    reviewed_at=reviewed_at,
                )
            except InvalidRatingError as exc:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field="rating",
                        reason=str(exc),
                    )
                )
                continue
            except EmptyFieldError as exc:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field=None,
                        reason=str(exc),
                    )
                )
                continue
            except DomainException as exc:
                rejected_errors.append(
                    RowErrorDetail(
                        line=line_num,
                        field=None,
                        reason=str(exc),
                    )
                )
                continue

            # Intra-file deduplication ONLY after valid Review construction
            key = (source_system, external_id)
            if key in seen_keys_in_file:
                file_skipped_count += 1
                continue

            seen_keys_in_file.add(key)
            valid_reviews.append(review)

        # Step 5 & 6: Persist valid reviews and finalize job
        total_rejected = len(rejected_errors)

        try:
            async with self._uow_factory() as uow:
                inserted_count, db_skipped_count = await uow.reviews.insert_many_if_not_exists(
                    valid_reviews
                )

                total_skipped = file_skipped_count + db_skipped_count
                total_rows = inserted_count + total_skipped + total_rejected

                # Use independent clone to execute complete() so original `job`
                # remains in PROCESSING until the commit succeeds.
                completed_job = copy.deepcopy(job)
                completed_job.complete(
                    rows_total=total_rows,
                    rows_imported=inserted_count,
                    rows_skipped=total_skipped,
                    rows_rejected=total_rejected,
                )

                await uow.import_jobs.update(completed_job)
                await uow.commit()

                # On successful commit, adopt completed job state
                job = completed_job

        except Exception as exc:
            logger.error(
                "Unexpected failure persisting reviews for job %s: %s",
                job.id,
                exc,
                exc_info=True,
            )
            # Original job is guaranteed to still be in PROCESSING!
            try:
                async with self._uow_factory() as uow:
                    job.fail(error_summary=f"Database error during persistence: {exc}")
                    await uow.import_jobs.update(job)
                    await uow.commit()
            except Exception as inner_exc:
                logger.error(
                    "Failed to record failure status for job %s: %s",
                    job.id,
                    inner_exc,
                )

            raise RuntimeError("Unexpected failure during review persistence") from exc

        return ImportReviewsResult(
            import_job_id=job.id,
            status=job.status,
            rows_total=job.rows_total,
            rows_imported=job.rows_imported,
            rows_skipped=job.rows_skipped,
            rows_rejected=job.rows_rejected,
            errors=rejected_errors[: self._max_error_details],
            error_summary=job.error_summary,
        )
