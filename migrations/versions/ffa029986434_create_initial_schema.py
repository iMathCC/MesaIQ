"""create initial schema

Revision ID: ffa029986434
Revises:
Create Date: 2026-11-08 22:19:30.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ffa029986434"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the initial MesaIQ tables and enable pgvector."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "restaurants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_restaurants")),
    )

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("rows_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_imported", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_rejected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name=op.f("ck_import_jobs_status_valid"),
        ),
        sa.CheckConstraint(
            "rows_total >= 0 AND rows_imported >= 0 AND rows_skipped >= 0 AND rows_rejected >= 0",
            name=op.f("ck_import_jobs_non_negative"),
        ),
        sa.CheckConstraint(
            "rows_total = rows_imported + rows_skipped + rows_rejected",
            name=op.f("ck_import_jobs_rows_total_balance"),
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name=op.f("fk_import_jobs_restaurant_id_restaurants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_jobs")),
    )
    op.create_index(
        "ix_import_jobs_restaurant_id",
        "import_jobs",
        ["restaurant_id"],
        unique=False,
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name=op.f("ck_reviews_rating_range")),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            name=op.f("fk_reviews_restaurant_id_restaurants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        sa.UniqueConstraint(
            "restaurant_id",
            "source_system",
            "external_id",
            name="uq_reviews_restaurant_source_external",
        ),
    )
    op.create_index(
        "ix_reviews_restaurant_id_reviewed_at",
        "reviews",
        ["restaurant_id", "reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the initial tables, keeping the shared vector extension."""
    op.drop_index("ix_reviews_restaurant_id_reviewed_at", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_import_jobs_restaurant_id", table_name="import_jobs")
    op.drop_table("import_jobs")
    op.drop_table("restaurants")
