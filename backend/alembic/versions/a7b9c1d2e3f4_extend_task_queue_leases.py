"""extend task queue leases

Revision ID: a7b9c1d2e3f4
Revises: e6f7a8b9c0d1
Create Date: 2026-07-07 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7b9c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_queue", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")))
    op.add_column("task_queue", sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("task_queue", sa.Column("available_at", sa.DateTime(), nullable=True))
    op.add_column("task_queue", sa.Column("locked_by", sa.String(), nullable=True))
    op.add_column("task_queue", sa.Column("locked_at", sa.DateTime(), nullable=True))
    op.add_column("task_queue", sa.Column("lease_until", sa.DateTime(), nullable=True))
    op.add_column("task_queue", sa.Column("resource_key", sa.String(), nullable=True))
    op.create_index("ix_task_queue_status_available", "task_queue", ["status", "available_at"])
    op.create_index("ix_task_queue_resource_status", "task_queue", ["resource_key", "status"])
    op.create_index("ix_task_queue_lease_until", "task_queue", ["lease_until"])


def downgrade() -> None:
    op.drop_index("ix_task_queue_lease_until", table_name="task_queue")
    op.drop_index("ix_task_queue_resource_status", table_name="task_queue")
    op.drop_index("ix_task_queue_status_available", table_name="task_queue")
    op.drop_column("task_queue", "resource_key")
    op.drop_column("task_queue", "lease_until")
    op.drop_column("task_queue", "locked_at")
    op.drop_column("task_queue", "locked_by")
    op.drop_column("task_queue", "available_at")
    op.drop_column("task_queue", "priority")
    op.drop_column("task_queue", "max_attempts")
