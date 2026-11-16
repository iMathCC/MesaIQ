"""SQLAlchemy implementation of RestaurantRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mesaiq.domain.entities.restaurant import Restaurant as RestaurantEntity
from mesaiq.infrastructure.database.models import Restaurant as RestaurantModel


class SqlAlchemyRestaurantRepository:
    """Repository adapter for Restaurant persistence using SQLAlchemy async."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, restaurant_id: UUID) -> RestaurantEntity | None:
        """Fetch a restaurant by its UUID and map to domain entity."""
        stmt = select(RestaurantModel).where(RestaurantModel.id == restaurant_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return RestaurantEntity(
            id=model.id,
            name=model.name,
            created_at=model.created_at,
        )
