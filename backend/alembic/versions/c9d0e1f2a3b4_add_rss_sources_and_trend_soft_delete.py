"""add RSS sources and Trend soft delete

Revision ID: c9d0e1f2a3b4
Revises: b8c0d1e2f3a4
Create Date: 2026-07-15 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_rss_source",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("item_limit", sa.Integer(), nullable=False, server_default=sa.text("8")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_trend_rss_source_url"),
    )
    op.create_index("ix_trend_rss_source_enabled", "trend_rss_source", ["enabled"])
    op.add_column("trend_item", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_trend_item_deleted_at", "trend_item", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_trend_item_deleted_at", table_name="trend_item")
    op.drop_column("trend_item", "deleted_at")
    op.drop_index("ix_trend_rss_source_enabled", table_name="trend_rss_source")
    op.drop_table("trend_rss_source")
