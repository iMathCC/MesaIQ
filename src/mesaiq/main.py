"""FastAPI application factory and command-line entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mesaiq.api.health import router as health_router
from mesaiq.api.routes.review_imports import router as review_imports_router
from mesaiq.config import Settings, get_settings
from mesaiq.infrastructure.database.session import create_engine, create_session_factory

API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "MesaIQ transforma avaliações de restaurantes em inteligência acionável, "
    "combinando métricas determinísticas e análise semântica fundamentada."
)


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    app_settings = settings or get_settings()
    _configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(app_settings)
        app.state.settings = app_settings
        app.state.db_engine = engine
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(review_imports_router, prefix="/api/v1")
    return app


def main() -> None:
    """Run the development server through the ``mesaiq`` console script."""
    import uvicorn

    uvicorn.run(
        "mesaiq.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
    )
