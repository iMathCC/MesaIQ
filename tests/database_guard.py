"""Validation helper for isolated PostgreSQL test database URL."""

import pytest
from sqlalchemy.engine import make_url


def validate_test_database_url(url: str | None) -> str:
    """Validate that the test database URL is provided, valid, and strictly targets 'mesaiq_test'.

    Security guards:
    - Fails if the URL cannot be parsed, without exposing input credentials.
    - Requires driver to be 'postgresql+asyncpg'.
    - Enforces strict allowlist: database name MUST be exactly 'mesaiq_test'.
    - Never prints passwords or full connection strings in failure messages.
    """
    if not url or not url.strip():
        pytest.skip("MESAIQ_TEST_DATABASE_URL not set. Skipping real PostgreSQL integration tests.")

    try:
        parsed_url = make_url(url.strip())
    except Exception:
        pytest.fail(
            "Integração bloqueada: URL de banco de dados inválida. "
            "A URL deve seguir o formato 'postgresql+asyncpg://...' apontando para 'mesaiq_test'."
        )

    if parsed_url.drivername != "postgresql+asyncpg":
        pytest.fail(
            f"Integração bloqueada: o driver configurado é '{parsed_url.drivername}'. "
            "Somente o driver 'postgresql+asyncpg' é permitido para testes de integração."
        )

    if parsed_url.database != "mesaiq_test":
        pytest.fail(
            f"Integração bloqueada: o banco alvo configurado é '{parsed_url.database}'. "
            "Somente o banco PostgreSQL 'mesaiq_test' pode ser utilizado."
        )

    return url.strip()
