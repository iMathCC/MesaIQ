"""Review domain entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mesaiq.domain.exceptions import EmptyFieldError, InvalidRatingError


@dataclass(frozen=True)
class Review:
    """Represents a customer review belonging to a restaurant."""

    restaurant_id: UUID
    source_system: str
    external_id: str
    rating: int
    content: str
    reviewed_at: datetime
    id: UUID = field(default_factory=uuid4)
    imported_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.source_system or not self.source_system.strip():
            raise EmptyFieldError("source_system cannot be empty")
        if not self.external_id or not self.external_id.strip():
            raise EmptyFieldError("external_id cannot be empty")
        if not self.content or not self.content.strip():
            raise EmptyFieldError("content cannot be empty")
        if self.rating < 1 or self.rating > 5:
            raise InvalidRatingError(f"Rating must be between 1 and 5, got {self.rating}")
        # Ensure reviewed_at is timezone-aware; if naive, assume UTC
        if self.reviewed_at.tzinfo is None:
            object.__setattr__(self, "reviewed_at", self.reviewed_at.replace(tzinfo=UTC))
        if self.imported_at.tzinfo is None:
            object.__setattr__(self, "imported_at", self.imported_at.replace(tzinfo=UTC))

    @property
    def logical_key(self) -> tuple[UUID, str, str]:
        """Composite logical uniqueness key."""
        return (self.restaurant_id, self.source_system, self.external_id)
