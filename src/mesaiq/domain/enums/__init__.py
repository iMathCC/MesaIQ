"""Domain-level enumerations."""

from enum import StrEnum


class ImportJobStatus(StrEnum):
    """Lifecycle status of an ImportJob."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
