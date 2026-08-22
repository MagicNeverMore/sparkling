"""add content topic series

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("content_topic", sa.Column("series", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_topic", "series")
