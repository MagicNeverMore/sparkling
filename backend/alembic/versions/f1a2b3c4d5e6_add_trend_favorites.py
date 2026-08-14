"""add Trend favorites

Revision ID: f1a2b3c4d5e6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-13 23:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trend_item",
        sa.Column("is_favorited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("trend_item", sa.Column("favorited_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_trend_item_auto_cleanup",
        "trend_item",
        ["deleted_at", "is_favorited", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trend_item_auto_cleanup", table_name="trend_item")
    op.drop_column("trend_item", "favorited_at")
    op.drop_column("trend_item", "is_favorited")
