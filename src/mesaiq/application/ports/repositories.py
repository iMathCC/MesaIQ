"""Repository ports (contracts) for MesaIQ data access."""

from typing import Protocol
from uuid import UUID

from mesaiq.domain.entities.import_job import ImportJob
from mesaiq.domain.entities.restaurant import Restaurant
from mesaiq.domain.entities.review import Review


class RestaurantRepository(Protocol):
    """Port for Restaurant persistence operations."""

    async def get_by_id(self, restaurant_id: UUID) -> Restaurant | None:
        """Fetch a restaurant by its UUID, or None if not found."""
        ...


class ReviewRepository(Protocol):
    """Port for Review persistence operations."""

    async def insert_many_if_not_exists(
        self,
        reviews: list[Review],
    ) -> tuple[int, int]:
        """Atomically insert reviews using PostgreSQL ON CONFLICT DO NOTHING.

        Returns:
            tuple[int, int]: (inserted_count, skipped_count)
        """
        ...


class ImportJobRepository(Protocol):
    """Port for ImportJob persistence operations."""

    async def create(self, job: ImportJob) -> ImportJob:
        """Persist a new ImportJob record."""
        ...

    async def update(self, job: ImportJob) -> ImportJob:
        """Update an existing ImportJob record."""
        ...

    async def get_by_id(self, job_id: UUID) -> ImportJob | None:
        """Fetch an ImportJob by its UUID."""
        ...
