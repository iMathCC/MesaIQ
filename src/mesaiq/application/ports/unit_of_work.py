"""Unit of Work interface for coordinating atomic transactions."""

from types import TracebackType
from typing import Protocol

from mesaiq.application.ports.repositories import (
    ImportJobRepository,
    RestaurantRepository,
    ReviewRepository,
)


class UnitOfWork(Protocol):
    """Port for transactional unit of work context."""

    restaurants: RestaurantRepository
    reviews: ReviewRepository
    import_jobs: ImportJobRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None:
        """Commit the current transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...
