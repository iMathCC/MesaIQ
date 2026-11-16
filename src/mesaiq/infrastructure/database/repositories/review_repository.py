"""SQLAlchemy implementation of ReviewRepository."""

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mesaiq.domain.entities.review import Review as ReviewEntity
from mesaiq.infrastructure.database.models import Review as ReviewModel

DEFAULT_BATCH_SIZE = 500


class SqlAlchemyReviewRepository:
    """Repository adapter for Review persistence using SQLAlchemy async and PostgreSQL."""

    def __init__(self, session: AsyncSession, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        self._session = session
        self._batch_size = batch_size

    async def insert_many_if_not_exists(
        self,
        reviews: list[ReviewEntity],
    ) -> tuple[int, int]:
        """Atomically insert reviews in batches using PostgreSQL ON CONFLICT DO NOTHING.

        Uses the composite unique constraint (restaurant_id, source_system, external_id).
        All batches execute within the same Unit of Work session/transaction.

        Returns:
            tuple[int, int]: (inserted_count, skipped_count)
        """
        if not reviews:
            return 0, 0

        total_inserted = 0

        for i in range(0, len(reviews), self._batch_size):
            batch = reviews[i : i + self._batch_size]
            values = [
                {
                    "id": review.id,
                    "restaurant_id": review.restaurant_id,
                    "source_system": review.source_system,
                    "external_id": review.external_id,
                    "rating": review.rating,
                    "content": review.content,
                    "reviewed_at": review.reviewed_at,
                    "imported_at": review.imported_at,
                }
                for review in batch
            ]

            stmt = (
                pg_insert(ReviewModel)
                .values(values)
                .on_conflict_do_nothing(constraint="uq_reviews_restaurant_source_external")
                .returning(ReviewModel.id)
            )

            result = await self._session.execute(stmt)
            inserted_rows = result.scalars().all()
            total_inserted += len(inserted_rows)

        total_skipped = len(reviews) - total_inserted
        return total_inserted, total_skipped
