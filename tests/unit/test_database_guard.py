"""Unit tests for the test database URL security guard (no database connection required)."""

import pytest

from tests.database_guard import validate_test_database_url


def test_guard_allows_valid_mesaiq_test_url() -> None:
    valid_url = "postgresql+asyncpg://mesaiq:secret_pass@localhost:5433/mesaiq_test"
    result = validate_test_database_url(valid_url)
    assert result == valid_url


def test_guard_blocks_dev_database_mesaiq() -> None:
    dev_url = "postgresql+asyncpg://mesaiq:secret_pass@localhost:5433/mesaiq"
    with pytest.raises(pytest.fail.Exception) as exc_info:
        validate_test_database_url(dev_url)

    error_msg = str(exc_info.value)
    assert "Somente o banco PostgreSQL 'mesaiq_test' pode ser utilizado" in error_msg
    assert "secret_pass" not in error_msg


def test_guard_blocks_postgres_database() -> None:
    postgres_url = "postgresql+asyncpg://postgres:pass@localhost:5433/postgres"
    with pytest.raises(pytest.fail.Exception) as exc_info:
        validate_test_database_url(postgres_url)

    error_msg = str(exc_info.value)
    assert "Somente o banco PostgreSQL 'mesaiq_test' pode ser utilizado" in error_msg
    assert "pass" not in error_msg


def test_guard_blocks_production_database() -> None:
    prod_url = "postgresql+asyncpg://admin:super_secret@remote:5432/production"
    with pytest.raises(pytest.fail.Exception) as exc_info:
        validate_test_database_url(prod_url)

    error_msg = str(exc_info.value)
    assert "Somente o banco PostgreSQL 'mesaiq_test' pode ser utilizado" in error_msg
    assert "super_secret" not in error_msg


def test_guard_blocks_invalid_driver() -> None:
    sync_url = "postgresql://mesaiq:pass@localhost:5433/mesaiq_test"
    with pytest.raises(pytest.fail.Exception) as exc_info:
        validate_test_database_url(sync_url)

    error_msg = str(exc_info.value)
    assert "Somente o driver 'postgresql+asyncpg' é permitido" in error_msg
    assert "pass" not in error_msg


def test_guard_blocks_malformed_url_without_exposing_secrets() -> None:
    bad_url = "not a valid url ://user:secret_token@bad"
    with pytest.raises(pytest.fail.Exception) as exc_info:
        validate_test_database_url(bad_url)

    error_msg = str(exc_info.value)
    assert "URL de banco de dados inválida" in error_msg
    assert "secret_token" not in error_msg


def test_guard_skips_when_url_is_none_or_empty() -> None:
    with pytest.raises(pytest.skip.Exception):
        validate_test_database_url(None)

    with pytest.raises(pytest.skip.Exception):
        validate_test_database_url("")
