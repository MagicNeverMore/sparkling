"""store hourly social media observations

Revision ID: b4c5d6e7f8a9
Revises: f3a4b5c6d7e8
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _observation_hour(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc_value.replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _column_details(table_name: str) -> dict[str, dict[str, object]]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"]: column for column in inspector.get_columns(table_name)}


def _unique_constraint_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """兼容已落 DDL、但 revision 未落库的中断部署。"""
    columns = _column_details("social_media_dataset")
    if "observation_hour" not in columns:
        op.add_column("social_media_dataset", sa.Column("observation_hour", sa.String(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, collected_at FROM social_media_dataset WHERE observation_hour IS NULL")
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text("UPDATE social_media_dataset SET observation_hour = :observation_hour WHERE id = :id"),
            {"id": row["id"], "observation_hour": _observation_hour(row["collected_at"])},
        )
    unique_constraints = _unique_constraint_names("social_media_dataset")
    column_is_nullable = bool(_column_details("social_media_dataset")["observation_hour"]["nullable"])
    with op.batch_alter_table("social_media_dataset") as batch_op:
        if "uq_social_media_dataset_account_date" in unique_constraints:
            batch_op.drop_constraint("uq_social_media_dataset_account_date", type_="unique")
        if column_is_nullable:
            batch_op.alter_column("observation_hour", existing_type=sa.String(), nullable=False)
        if "uq_social_media_dataset_account_observation_hour" not in unique_constraints:
            batch_op.create_unique_constraint(
                "uq_social_media_dataset_account_observation_hour",
                ["platform", "external_account_id", "observation_hour"],
            )

    indexes = _index_names("social_media_dataset")
    if "ix_social_media_dataset_latest" in indexes:
        op.drop_index("ix_social_media_dataset_latest", table_name="social_media_dataset")
    if "ix_social_media_dataset_latest_observation" not in indexes:
        op.create_index(
            "ix_social_media_dataset_latest_observation",
            "social_media_dataset",
            ["platform", "external_account_id", "observation_hour"],
        )


def downgrade() -> None:
    """回退到每日快照时，每个日期仅保留最后一次小时观测。"""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, platform, external_account_id, metric_date, observation_hour "
            "FROM social_media_dataset "
            "ORDER BY observation_hour DESC, collected_at DESC, id DESC"
        )
    ).mappings()
    retained_dates: set[tuple[str, str, str]] = set()
    removed_dataset_ids: list[int] = []
    for row in rows:
        key = (row["platform"], row["external_account_id"], row["metric_date"])
        if key in retained_dates:
            removed_dataset_ids.append(row["id"])
        else:
            retained_dates.add(key)

    for dataset_id in removed_dataset_ids:
        # `social_media_video_snapshot` 的外键在历史 SQLite schema 未必启用级联，
        # 因此显式删除，避免回退时留下孤儿记录。
        bind.execute(
            sa.text("DELETE FROM social_media_video_snapshot WHERE dataset_id = :dataset_id"),
            {"dataset_id": dataset_id},
        )
        bind.execute(
            sa.text("DELETE FROM social_media_dataset WHERE id = :dataset_id"),
            {"dataset_id": dataset_id},
        )

    op.drop_index("ix_social_media_dataset_latest_observation", table_name="social_media_dataset")
    with op.batch_alter_table("social_media_dataset") as batch_op:
        batch_op.drop_constraint(
            "uq_social_media_dataset_account_observation_hour", type_="unique"
        )
        batch_op.drop_column("observation_hour")
        batch_op.create_unique_constraint(
            "uq_social_media_dataset_account_date",
            ["platform", "external_account_id", "metric_date"],
        )
    op.create_index(
        "ix_social_media_dataset_latest",
        "social_media_dataset",
        ["platform", "external_account_id", "metric_date"],
    )
