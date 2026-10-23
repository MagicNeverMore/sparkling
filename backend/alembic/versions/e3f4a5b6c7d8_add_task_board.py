"""Persist task execution board independently of calendar dates."""
from alembic import op
import sqlalchemy as sa
from app.logger import get_logger

logger = get_logger(__name__)

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_task", sa.Column("board_status", sa.String(), nullable=False, server_default="backlog"))
    op.add_column("user_task", sa.Column("board_position", sa.Integer(), nullable=False, server_default="0"))
    logger.info("任务看板 schema 已添加 revision=%s default_status=%s", revision, "backlog")


def downgrade() -> None:
    with op.batch_alter_table("user_task") as batch:
        batch.drop_column("board_position")
        batch.drop_column("board_status")
    logger.info("任务看板 schema 已回退 revision=%s", revision)
