"""finalize social media run states

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_queue", sa.Column("dedupe_key", sa.String(), nullable=True))
    # worker 尚未启动，旧版 active Social Media task 均属于中断执行；不得带入新状态机重试。
    op.execute(
        """
        UPDATE task_queue
        SET status = 'failed',
            max_attempts = 1,
            last_error = COALESCE(last_error, '旧版本未完成任务已终止，由新调度周期重新创建'),
            locked_by = NULL,
            locked_at = NULL,
            lease_until = NULL
        WHERE task_type = 'social_media_collect'
          AND status IN ('pending', 'running')
        """
    )
    op.execute(
        "UPDATE task_queue SET max_attempts = 1 "
        "WHERE task_type = 'social_media_collect' AND max_attempts <> 1"
    )
    # 历史版本在多 worker 竞争时可能留下同 resource 的 running task；只保留最早一条。
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY resource_key ORDER BY created_at ASC, id ASC
                   ) AS row_number
            FROM task_queue
            WHERE status = 'running' AND resource_key IS NOT NULL
        )
        UPDATE task_queue
        SET status = 'pending',
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
        sqlite_where=sa.text("dedupe_key IS NOT NULL AND status IN ('pending', 'running')"),
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND status IN ('pending', 'running')"),
    )
    op.create_index(
        "uq_task_queue_running_resource",
        "task_queue",
        ["resource_key"],
        unique=True,
        sqlite_where=sa.text("resource_key IS NOT NULL AND status = 'running'"),
        postgresql_where=sa.text("resource_key IS NOT NULL AND status = 'running'"),
    )

    # migration 发生在 worker 启动前；旧 pending/running 都是不再执行的历史记录。
    op.execute(
        """
        UPDATE social_media_sync_run
        SET status = 'failed',
            error = COALESCE(error, '旧版本未完成记录已终止，请重新触发同步'),
            finished_at = COALESCE(finished_at, updated_at, created_at)
        WHERE status IN ('pending', 'running')
        """
    )
    with op.batch_alter_table("social_media_sync_run") as batch_op:
        batch_op.create_check_constraint(
            "ck_social_media_sync_run_status",
            "status IN ('running', 'done', 'failed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("social_media_sync_run") as batch_op:
        batch_op.drop_constraint("ck_social_media_sync_run_status", type_="check")
    op.drop_index("uq_task_queue_running_resource", table_name="task_queue")
    op.drop_index("uq_task_queue_active_dedupe", table_name="task_queue")
    with op.batch_alter_table("task_queue") as batch_op:
        batch_op.drop_column("dedupe_key")
