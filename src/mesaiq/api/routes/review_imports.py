"""API routes for review management and CSV import."""

import logging
from collections.abc import Callable
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mesaiq.application.dtos.import_reviews import ImportReviewsResult
from mesaiq.application.ports.unit_of_work import UnitOfWork
from mesaiq.application.use_cases.import_reviews import (
    ImportReviewsUseCase,
    RestaurantNotFoundError,
)
from mesaiq.config import Settings
from mesaiq.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from mesaiq.infrastructure.parsers.csv_review_parser import CsvReviewParserImpl

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/restaurants",
    tags=["reviews"],
)


def get_settings_dep(request: Request) -> Settings:
    """Retrieve app settings from FastAPI app state."""
    settings: Settings = request.app.state.settings
    return settings


def get_uow_factory(request: Request) -> Callable[[], UnitOfWork]:
    """Provide a UnitOfWork factory bound to the application's session factory."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


@router.post(
    "/{restaurant_id}/reviews/imports",
    response_model=ImportReviewsResult,
    status_code=status.HTTP_201_CREATED,
    summary="Import customer reviews via CSV file",
)
async def import_reviews(
    restaurant_id: UUID,
    file: UploadFile = File(..., description="CSV file with customer reviews"),  # noqa: B008
    settings: Settings = Depends(get_settings_dep),  # noqa: B008
    uow_factory: Callable[[], UnitOfWork] = Depends(get_uow_factory),  # noqa: B008
) -> ImportReviewsResult:
    """Upload and process a CSV file containing reviews for a restaurant.

    Validates:
    - Target restaurant existence (404 if not found).
    - File presence and CSV extension (.csv).
    - File size within configured limit (413 if exceeded).
    - Structured deduplication and row validation.
    """
    # 1. Validate filename / extension
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid file format. File must have a .csv extension.",
        )

    # 2. Read content enforcing size limit
    max_size = settings.max_upload_size_bytes
    # Read chunk-by-chunk to prevent loading unlimited content into memory
    content_chunks: list[bytes] = []
    total_read = 0
    chunk_size = 64 * 1024  # 64 KB chunks

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_size:
            max_mb = max_size // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {max_size} bytes ({max_mb} MB).",
            )
        content_chunks.append(chunk)

    content = b"".join(content_chunks)

    # 3. Instantiate parser and use case
    parser = CsvReviewParserImpl()
    use_case = ImportReviewsUseCase(
        uow_factory=uow_factory,
        parser=parser,
    )

    try:
        result = await use_case.execute(
            restaurant_id=restaurant_id,
            filename=filename,
            content=content,
        )
    except RestaurantNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Restaurant with ID '{restaurant_id}' was not found.",
        ) from err
    except Exception as exc:
        logger.error(
            "Unexpected error importing reviews for restaurant %s: %s",
            restaurant_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the import.",
        ) from exc

    return result
