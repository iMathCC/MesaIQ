"""Unit tests for the SQLAlchemy metadata (no database connection required)."""

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)

from mesaiq.infrastructure.database.base import Base
from mesaiq.infrastructure.database.models import ImportJob, Restaurant, Review  # noqa: F401


def test_initial_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {"restaurants", "reviews", "import_jobs"}


def test_primary_keys() -> None:
    for table_name in ("restaurants", "reviews", "import_jobs"):
        table = Base.metadata.tables[table_name]
        assert list(table.primary_key.columns.keys()) == ["id"]


def test_restaurant_columns() -> None:
    table = Base.metadata.tables["restaurants"]

    assert isinstance(table.c.name.type, String)
    assert table.c.name.nullable is False
    assert isinstance(table.c.created_at.type, DateTime)
    assert table.c.created_at.type.timezone is True
    assert table.c.created_at.nullable is False


def test_review_columns_and_types() -> None:
    table = Base.metadata.tables["reviews"]

    assert isinstance(table.c.rating.type, SmallInteger)
    assert table.c.rating.nullable is False
    assert isinstance(table.c.content.type, Text)
    assert table.c.content.nullable is False
    assert isinstance(table.c.reviewed_at.type, DateTime)
    assert table.c.reviewed_at.type.timezone is True
    assert isinstance(table.c.imported_at.type, DateTime)
    assert table.c.imported_at.type.timezone is True


def test_review_foreign_key() -> None:
    table = Base.metadata.tables["reviews"]
    foreign_keys = list(table.foreign_keys)

    assert len(foreign_keys) == 1
    foreign_key = foreign_keys[0]
    assert foreign_key.target_fullname == "restaurants.id"
    assert foreign_key.ondelete == "CASCADE"
    assert foreign_key.constraint is not None
    assert foreign_key.constraint.name == "fk_reviews_restaurant_id_restaurants"


def test_review_uniqueness_constraint() -> None:
    table = Base.metadata.tables["reviews"]
    unique_constraints = [
        constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
    ]

    assert len(unique_constraints) == 1
    constraint = unique_constraints[0]
    assert constraint.name == "uq_reviews_restaurant_source_external"
    assert list(constraint.columns.keys()) == [
        "restaurant_id",
        "source_system",
        "external_id",
    ]


def test_review_rating_check_constraint() -> None:
    table = Base.metadata.tables["reviews"]
    check = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_reviews_rating_range"
    )

    assert "rating >= 1" in str(check.sqltext)
    assert "rating <= 5" in str(check.sqltext)


def test_review_lookup_index() -> None:
    table = Base.metadata.tables["reviews"]

    assert "ix_reviews_restaurant_id_reviewed_at" in {index.name for index in table.indexes}
    index = next(
        index for index in table.indexes if index.name == "ix_reviews_restaurant_id_reviewed_at"
    )
    assert [column.name for column in index.columns] == ["restaurant_id", "reviewed_at"]


def test_import_job_columns_and_checks() -> None:
    table = Base.metadata.tables["import_jobs"]
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert isinstance(table.c.rows_total.type, Integer)
    assert isinstance(table.c.status.type, String)
    assert table.c.finished_at.nullable is True
    assert table.c.error_summary.nullable is True
    assert check_names == {
        "ck_import_jobs_status_valid",
        "ck_import_jobs_non_negative",
        "ck_import_jobs_rows_total_balance",
    }


def test_import_job_status_check_lists_allowed_states() -> None:
    table = Base.metadata.tables["import_jobs"]
    check = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_import_jobs_status_valid"
    )
    sql = str(check.sqltext)

    for status in ("PENDING", "PROCESSING", "COMPLETED", "FAILED"):
        assert status in sql


def test_import_job_balance_check() -> None:
    table = Base.metadata.tables["import_jobs"]
    check = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_import_jobs_rows_total_balance"
    )

    assert "rows_total = rows_imported + rows_skipped + rows_rejected" in str(check.sqltext)


def test_import_job_foreign_key_and_index() -> None:
    table = Base.metadata.tables["import_jobs"]
    foreign_keys = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].name == "fk_import_jobs_restaurant_id_restaurants"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert "ix_import_jobs_restaurant_id" in {index.name for index in table.indexes}
