"""add content topics and publication links

Revision ID: b9c0d1e2f3a4
Revises: a6b7c8d9e0f1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_topic",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String()),
        sa.Column("status", sa.String(), nullable=False, server_default="not_started"),
        sa.Column("scheduled_at", sa.DateTime()),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("cover_path", sa.String()),
        sa.Column("task_id", sa.String()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_content_topic_status", "content_topic", ["status"])
    op.create_index("ix_content_topic_category", "content_topic", ["category"])
    op.create_table(
        "content_topic_publication",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("topic_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("social_media_video_id", sa.String()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["content_topic.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["social_media_video_id"], ["social_media_video.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_content_topic_publication_topic", "content_topic_publication", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_content_topic_publication_topic", table_name="content_topic_publication")
    op.drop_table("content_topic_publication")
    op.drop_index("ix_content_topic_category", table_name="content_topic")
    op.drop_index("ix_content_topic_status", table_name="content_topic")
    op.drop_table("content_topic")
