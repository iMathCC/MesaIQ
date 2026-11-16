"""SQLAlchemy implementation of UnitOfWork."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mesaiq.application.ports.unit_of_work import UnitOfWork
from mesaiq.infrastructure.database.repositories.import_job_repository import (
    SqlAlchemyImportJobRepository,
)
from mesaiq.infrastructure.database.repositories.restaurant_repository import (
    SqlAlchemyRestaurantRepository,
)
from mesaiq.infrastructure.database.repositories.review_repository import (
    SqlAlchemyReviewRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy-backed Unit of Work for transactional management."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.restaurants = SqlAlchemyRestaurantRepository(self._session)
        self.reviews = SqlAlchemyReviewRepository(self._session)
        self.import_jobs = SqlAlchemyImportJobRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc_type is not None:
                await self.rollback()
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        """Commit the current active transaction."""
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        """Rollback changes in the current session."""
        if self._session is not None:
            await self._session.rollback()
