"""DTOs for review importation."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mesaiq.domain.enums import ImportJobStatus


@dataclass(frozen=True)
class RawReviewRow:
    """Raw record extracted from the CSV file by the parser.

    Preserves the original 1-based physical line number for precise reporting.
    """

    line_number: int
    data: dict[str, str]


class RowErrorDetail(BaseModel):
    """Detailed error explanation for an invalid CSV row."""

    model_config = ConfigDict(frozen=True)

    line: int = Field(description="1-based line number in the CSV file")
    field: str | None = Field(
        default=None,
        description="Field name where error occurred, if identifiable",
    )
    reason: str = Field(description="Human-readable description of why the row was rejected")


class ImportReviewsResult(BaseModel):
    """Result of a CSV review import operation."""

    model_config = ConfigDict(frozen=True)

    import_job_id: UUID = Field(description="UUID of the persisted ImportJob audit record")
    status: ImportJobStatus = Field(
        description="Final status of the import job (COMPLETED or FAILED)"
    )
    rows_total: int = Field(description="Total rows processed (imported + skipped + rejected)")
    rows_imported: int = Field(description="New reviews successfully saved to the database")
    rows_skipped: int = Field(description="Reviews skipped due to duplication in file or database")
    rows_rejected: int = Field(description="Rows rejected due to structural or validation errors")
    errors: list[RowErrorDetail] = Field(
        default_factory=list,
        description="List of row errors (truncated to max_error_details)",
    )
    error_summary: str | None = Field(
        default=None,
        description="Summary of structural failure, if the entire file failed",
    )
