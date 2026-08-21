"""repair task queue dedupe schema drift

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """修复 revision 已前进、但关键 DDL 未落库的异常部署。"""
    if "dedupe_key" not in _column_names("task_queue"):
        op.add_column("task_queue", sa.Column("dedupe_key", sa.String(), nullable=True))

    indexes = _index_names("task_queue")
    if "uq_task_queue_active_dedupe" not in indexes:
        # schema drift 期间可能已有并发任务；保留最早一条，其余终结后再恢复唯一约束。
        op.execute(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY dedupe_key ORDER BY created_at ASC, id ASC
                       ) AS row_number
                FROM task_queue
                WHERE dedupe_key IS NOT NULL
                  AND status IN ('pending', 'running')
            )
            UPDATE task_queue
            SET status = 'failed',
                last_error = COALESCE(last_error, 'schema 修复时终止重复 active task'),
                locked_by = NULL,
                locked_at = NULL,
                lease_until = NULL
            WHERE id IN (SELECT id FROM ranked WHERE row_number > 1)
            """
        )
        op.create_index(
            "uq_task_queue_active_dedupe",
            "task_queue",
            ["dedupe_key"],
            unique=True,
            sqlite_where=sa.text(
                "dedupe_key IS NOT NULL AND status IN ('pending', 'running')"
            ),
            postgresql_where=sa.text(
                "dedupe_key IS NOT NULL AND status IN ('pending', 'running')"
            ),
        )
    if "uq_task_queue_running_resource" not in indexes:
        op.execute(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY resource_key ORDER BY created_at ASC, id ASC
                       ) AS row_number
                FROM task_queue
                WHERE resource_key IS NOT NULL AND status = 'running'
            )
            UPDATE task_queue
            SET status = 'failed',
                last_error = COALESCE(last_error, 'schema 修复时终止重复 running task'),
                locked_by = NULL,
                locked_at = NULL,
                lease_until = NULL
            WHERE id IN (SELECT id FROM ranked WHERE row_number > 1)
            """
        )
        op.create_index(
            "uq_task_queue_running_resource",
            "task_queue",
            ["resource_key"],
            unique=True,
            sqlite_where=sa.text("resource_key IS NOT NULL AND status = 'running'"),
            postgresql_where=sa.text("resource_key IS NOT NULL AND status = 'running'"),
        )


def downgrade() -> None:
    # 该 migration 只修复 schema drift；原始 DDL 的 downgrade 仍由 e2f3a4b5c6d7 负责。
    pass
