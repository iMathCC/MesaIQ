"""ImportJob domain entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mesaiq.domain.enums import ImportJobStatus
from mesaiq.domain.exceptions import (
    InconsistentCountersError,
    InvalidImportJobStateError,
)


@dataclass
class ImportJob:
    """Represents an audit and execution record for a CSV import batch."""

    restaurant_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: ImportJobStatus = ImportJobStatus.PENDING
    rows_total: int = 0
    rows_imported: int = 0
    rows_skipped: int = 0
    rows_rejected: int = 0
    error_summary: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        self._validate_counters()

    def _validate_counters(self) -> None:
        if (
            self.rows_total < 0
            or self.rows_imported < 0
            or self.rows_skipped < 0
            or self.rows_rejected < 0
        ):
            raise InconsistentCountersError("Row counters cannot be negative")

        if self.rows_total != (self.rows_imported + self.rows_skipped + self.rows_rejected):
            raise InconsistentCountersError(
                f"rows_total ({self.rows_total}) must equal "
                f"rows_imported ({self.rows_imported}) + "
                f"rows_skipped ({self.rows_skipped}) + "
                f"rows_rejected ({self.rows_rejected})"
            )

    def start_processing(self) -> None:
        """Transition job from PENDING to PROCESSING."""
        if self.status != ImportJobStatus.PENDING:
            raise InvalidImportJobStateError(
                f"Cannot start processing job in status {self.status.value}"
            )
        self.status = ImportJobStatus.PROCESSING

    def complete(
        self,
        *,
        rows_total: int,
        rows_imported: int,
        rows_skipped: int,
        rows_rejected: int,
        finished_at: datetime | None = None,
    ) -> None:
        """Complete the import job with verified counters."""
        if self.status != ImportJobStatus.PROCESSING:
            raise InvalidImportJobStateError(
                f"Cannot complete job in status {self.status.value}. "
                "Job must be in PROCESSING state."
            )
        self.rows_total = rows_total
        self.rows_imported = rows_imported
        self.rows_skipped = rows_skipped
        self.rows_rejected = rows_rejected
        self._validate_counters()
        self.status = ImportJobStatus.COMPLETED
        self.finished_at = finished_at or datetime.now(UTC)

    def fail(
        self,
        error_summary: str,
        *,
        rows_total: int = 0,
        rows_imported: int = 0,
        rows_skipped: int = 0,
        rows_rejected: int = 0,
        finished_at: datetime | None = None,
    ) -> None:
        """Mark the import job as failed."""
        if self.status in (ImportJobStatus.COMPLETED, ImportJobStatus.FAILED):
            raise InvalidImportJobStateError(
                f"Cannot fail job already in terminal status {self.status.value}"
            )
        self.rows_total = rows_total
        self.rows_imported = rows_imported
        self.rows_skipped = rows_skipped
        self.rows_rejected = rows_rejected
        self._validate_counters()
        self.status = ImportJobStatus.FAILED
        self.error_summary = error_summary
        self.finished_at = finished_at or datetime.now(UTC)
