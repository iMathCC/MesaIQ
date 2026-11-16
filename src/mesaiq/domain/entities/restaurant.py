"""Restaurant domain entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mesaiq.domain.exceptions import EmptyFieldError


@dataclass(frozen=True)
class Restaurant:
    """Represents a restaurant in MesaIQ."""

    name: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise EmptyFieldError("Restaurant name cannot be empty")
