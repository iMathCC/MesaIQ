"""SQLAlchemy implementation of ImportJobRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mesaiq.domain.entities.import_job import ImportJob as ImportJobEntity
from mesaiq.domain.enums import ImportJobStatus
from mesaiq.domain.exceptions import ImportJobNotFoundError
from mesaiq.infrastructure.database.models import ImportJob as ImportJobModel


class SqlAlchemyImportJobRepository:
    """Repository adapter for ImportJob persistence using SQLAlchemy async."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job: ImportJobEntity) -> ImportJobEntity:
        """Persist a new ImportJob record."""
        model = ImportJobModel(
            id=job.id,
            restaurant_id=job.restaurant_id,
            status=job.status.value,
            rows_total=job.rows_total,
            rows_imported=job.rows_imported,
            rows_skipped=job.rows_skipped,
            rows_rejected=job.rows_rejected,
            error_summary=job.error_summary,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        self._session.add(model)
        await self._session.flush()
        return job

    async def update(self, job: ImportJobEntity) -> ImportJobEntity:
        """Update an existing ImportJob record.

        Raises:
            ImportJobNotFoundError: If the job record does not exist in the database.
        """
        stmt = select(ImportJobModel).where(ImportJobModel.id == job.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ImportJobNotFoundError(f"ImportJob with ID '{job.id}' not found")

        model.status = job.status.value
        model.rows_total = job.rows_total
        model.rows_imported = job.rows_imported
        model.rows_skipped = job.rows_skipped
        model.rows_rejected = job.rows_rejected
        model.error_summary = job.error_summary
        model.finished_at = job.finished_at
        await self._session.flush()
        return job

    async def get_by_id(self, job_id: UUID) -> ImportJobEntity | None:
        """Fetch an ImportJob by its UUID."""
        stmt = select(ImportJobModel).where(ImportJobModel.id == job_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return ImportJobEntity(
            id=model.id,
            restaurant_id=model.restaurant_id,
            status=ImportJobStatus(model.status),
            rows_total=model.rows_total,
            rows_imported=model.rows_imported,
            rows_skipped=model.rows_skipped,
            rows_rejected=model.rows_rejected,
            error_summary=model.error_summary,
            started_at=model.started_at,
            finished_at=model.finished_at,
        )
