"""split social media videos from metrics

Revision ID: a6b7c8d9e0f1
Revises: c5d6e7f8a9b0
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """丢弃旧批次快照；新的同步会重新写入基础视频与最近十天指标。"""
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "social_media_video_snapshot" in tables:
        op.drop_table("social_media_video_snapshot")
    if "social_media_dataset" in tables:
        op.drop_table("social_media_dataset")

    op.create_table(
        "social_media_video",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("external_account_id", sa.String(), nullable=False),
        sa.Column("external_video_id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("platform", "external_video_id", name="uq_social_media_video_platform_external"),
    )
    op.create_index(
        "ix_social_media_video_published_at", "social_media_video", ["published_at"]
    )
    op.create_table(
        "social_media_video_metric",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("video_id", sa.String(), nullable=False),
        sa.Column("data_date", sa.String(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("ctr", sa.Float()),
        sa.Column("average_view_duration_seconds", sa.Float()),
        sa.Column("average_view_percentage", sa.Float()),
        sa.Column("subscribers_gained", sa.Integer(), nullable=False),
        sa.Column("subscribers_lost", sa.Integer(), nullable=False),
        sa.Column("net_subscribers", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["social_media_video.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("video_id", "data_date", name="uq_social_media_video_metric_date"),
    )
    op.create_index(
        "ix_social_media_video_metric_data_date", "social_media_video_metric", ["data_date"]
    )


def downgrade() -> None:
    raise NotImplementedError("社媒视频快照迁移会删除旧数据，不能安全回退")
