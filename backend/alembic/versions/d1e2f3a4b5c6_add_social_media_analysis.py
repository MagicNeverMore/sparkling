"""add social media analysis

Revision ID: d1e2f3a4b5c6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-19 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_media_dataset",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("external_account_id", sa.String(), nullable=False),
        sa.Column("metric_date", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "external_account_id",
            "metric_date",
            name="uq_social_media_dataset_account_date",
        ),
    )
    op.create_index(
        "ix_social_media_dataset_latest",
        "social_media_dataset",
        ["platform", "external_account_id", "metric_date"],
    )
    op.create_table(
        "social_media_video_snapshot",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("external_video_id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("average_view_duration_seconds", sa.Float(), nullable=True),
        sa.Column("average_view_percentage", sa.Float(), nullable=True),
        sa.Column("subscribers_gained", sa.Integer(), nullable=False),
        sa.Column("subscribers_lost", sa.Integer(), nullable=False),
        sa.Column("net_subscribers", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["social_media_dataset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "external_video_id", name="uq_social_media_video_dataset"),
    )
    op.create_index(
        "ix_social_media_video_dataset",
        "social_media_video_snapshot",
        ["dataset_id"],
    )
    op.create_table(
        "social_media_sync_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("external_account_id", sa.String(), nullable=True),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("metric_date", sa.String(), nullable=True),
        sa.Column("video_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_media_sync_run_created", "social_media_sync_run", ["created_at"])
    op.create_index("ix_social_media_sync_run_status", "social_media_sync_run", ["status"])


def downgrade() -> None:
    op.drop_index("ix_social_media_sync_run_status", table_name="social_media_sync_run")
    op.drop_index("ix_social_media_sync_run_created", table_name="social_media_sync_run")
    op.drop_table("social_media_sync_run")
    op.drop_index("ix_social_media_video_dataset", table_name="social_media_video_snapshot")
    op.drop_table("social_media_video_snapshot")
    op.drop_index("ix_social_media_dataset_latest", table_name="social_media_dataset")
    op.drop_table("social_media_dataset")
