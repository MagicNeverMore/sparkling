"""store social media datasets by data date

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_names() -> set[str]:
    return {
        item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints("social_media_dataset")
        if item.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("social_media_dataset")}
    if "data_date" not in columns:
        op.add_column("social_media_dataset", sa.Column("data_date", sa.String(), nullable=True))
    bind.execute(sa.text("UPDATE social_media_dataset SET data_date = metric_date WHERE data_date IS NULL"))

    rows = bind.execute(sa.text(
        "SELECT id, platform, external_account_id, data_date FROM social_media_dataset "
        "ORDER BY collected_at DESC, updated_at DESC, id DESC"
    )).mappings()
    retained: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row["platform"], row["external_account_id"], row["data_date"])
        if key in retained:
            bind.execute(sa.text("DELETE FROM social_media_video_snapshot WHERE dataset_id = :id"), {"id": row["id"]})
            bind.execute(sa.text("DELETE FROM social_media_dataset WHERE id = :id"), {"id": row["id"]})
        else:
            retained.add(key)

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("social_media_dataset")}
    if "ix_social_media_dataset_latest_observation" in indexes:
        op.drop_index("ix_social_media_dataset_latest_observation", table_name="social_media_dataset")

    constraints = _constraint_names()
    with op.batch_alter_table("social_media_dataset") as batch_op:
        if "uq_social_media_dataset_account_observation_hour" in constraints:
            batch_op.drop_constraint("uq_social_media_dataset_account_observation_hour", type_="unique")
        batch_op.alter_column("data_date", existing_type=sa.String(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_social_media_dataset_account_data_date",
            ["platform", "external_account_id", "data_date"],
        )
        if "metric_date" in columns:
            batch_op.drop_column("metric_date")
        if "observation_hour" in columns:
            batch_op.drop_column("observation_hour")
    op.create_index(
        "ix_social_media_dataset_latest_data_date",
        "social_media_dataset",
        ["platform", "external_account_id", "data_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_social_media_dataset_latest_data_date", table_name="social_media_dataset")
    with op.batch_alter_table("social_media_dataset") as batch_op:
        batch_op.drop_constraint("uq_social_media_dataset_account_data_date", type_="unique")
        batch_op.add_column(sa.Column("metric_date", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("observation_hour", sa.String(), nullable=True))

    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE social_media_dataset "
        "SET metric_date = data_date, observation_hour = data_date || 'T00:00:00Z'"
    ))
    with op.batch_alter_table("social_media_dataset") as batch_op:
        batch_op.alter_column("metric_date", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("observation_hour", existing_type=sa.String(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_social_media_dataset_account_observation_hour",
            ["platform", "external_account_id", "observation_hour"],
        )
        batch_op.drop_column("data_date")
    op.create_index(
        "ix_social_media_dataset_latest_observation",
        "social_media_dataset",
        ["platform", "external_account_id", "observation_hour"],
    )
