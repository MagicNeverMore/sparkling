"""add trend feature

Revision ID: f0e1d2c3b4a5
Revises: d8e1f2a3b4c5
Create Date: 2026-07-05 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, Sequence[str], None] = "d8e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_item",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("scoring_reason", sa.Text(), nullable=True),
        sa.Column("core_insight", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("resources_json", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index("ix_trend_item_last_seen_at", "trend_item", ["last_seen_at"])
    op.create_index("ix_trend_item_category", "trend_item", ["category"])

    op.create_table(
        "trend_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("saved_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trend_run_created_at", "trend_run", ["created_at"])
    op.create_index("ix_trend_run_status", "trend_run", ["status"])

    op.add_column("settings", sa.Column("trend_brand_prompt", sa.Text(), nullable=True))
    op.add_column("settings", sa.Column("trend_base_url", sa.String(), nullable=True))
    op.add_column("settings", sa.Column("trend_api_key", sa.String(), nullable=True))
    op.add_column("settings", sa.Column("trend_model", sa.String(), nullable=True))
    op.add_column("settings", sa.Column("trend_source_config", sa.Text(), nullable=True))
    op.add_column(
        "settings",
        sa.Column("trend_score_threshold", sa.Float(), nullable=False, server_default=sa.text("70")),
    )
    op.add_column(
        "settings",
        sa.Column("trend_result_limit", sa.Integer(), nullable=False, server_default=sa.text("20")),
    )
    op.add_column(
        "settings",
        sa.Column("trend_schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "settings",
        sa.Column("trend_schedule_frequency", sa.String(), nullable=False, server_default="daily"),
    )
    op.add_column(
        "settings",
        sa.Column("trend_schedule_time", sa.String(), nullable=False, server_default="09:00"),
    )
    op.add_column("settings", sa.Column("trend_last_run_at", sa.DateTime(), nullable=True))
    op.add_column("settings", sa.Column("trend_next_run_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "trend_next_run_at")
    op.drop_column("settings", "trend_last_run_at")
    op.drop_column("settings", "trend_schedule_time")
    op.drop_column("settings", "trend_schedule_frequency")
    op.drop_column("settings", "trend_schedule_enabled")
    op.drop_column("settings", "trend_result_limit")
    op.drop_column("settings", "trend_score_threshold")
    op.drop_column("settings", "trend_source_config")
    op.drop_column("settings", "trend_model")
    op.drop_column("settings", "trend_api_key")
    op.drop_column("settings", "trend_base_url")
    op.drop_column("settings", "trend_brand_prompt")

    op.drop_index("ix_trend_run_status", table_name="trend_run")
    op.drop_index("ix_trend_run_created_at", table_name="trend_run")
    op.drop_table("trend_run")

    op.drop_index("ix_trend_item_category", table_name="trend_item")
    op.drop_index("ix_trend_item_last_seen_at", table_name="trend_item")
    op.drop_table("trend_item")
