"""Add optional editorial performance rating."""
from alembic import op
import sqlalchemy as sa
from app.logger import get_logger

logger = get_logger(__name__)
revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_topic", sa.Column("performance_rating", sa.String(), nullable=True))
    logger.info("选题表现字段已添加 revision=%s", revision)


def downgrade() -> None:
    with op.batch_alter_table("content_topic") as batch:
        batch.drop_column("performance_rating")
    logger.info("选题表现字段已移除 revision=%s", revision)
