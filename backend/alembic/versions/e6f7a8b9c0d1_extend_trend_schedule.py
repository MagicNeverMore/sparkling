"""extend trend schedule settings

Revision ID: e6f7a8b9c0d1
Revises: f0e1d2c3b4a5
Create Date: 2026-07-06 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "f0e1d2c3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("trend_schedule_mode", sa.String(), nullable=False, server_default="weekly"),
    )
    op.add_column("settings", sa.Column("trend_schedule_days_json", sa.Text(), nullable=True))
    op.add_column(
        "settings",
        sa.Column("trend_schedule_interval_hours", sa.Integer(), nullable=False, server_default=sa.text("24")),
    )


def downgrade() -> None:
    op.drop_column("settings", "trend_schedule_interval_hours")
    op.drop_column("settings", "trend_schedule_days_json")
    op.drop_column("settings", "trend_schedule_mode")
