"""Add editorial retrospective notes."""
from alembic import op
import sqlalchemy as sa
from app.logger import get_logger

logger = get_logger(__name__)
revision = "a5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_topic", sa.Column("retrospective", sa.Text(), nullable=True))
    logger.info("选题复盘字段已添加 revision=%s", revision)


def downgrade() -> None:
    with op.batch_alter_table("content_topic") as batch:
        batch.drop_column("retrospective")
    logger.info("选题复盘字段已移除 revision=%s", revision)
