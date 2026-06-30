"""extend atom_embedding lifecycle metadata

Revision ID: d8e1f2a3b4c5
Revises: b72132d3c5c2
Create Date: 2026-06-30 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "b72132d3c5c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("atom_embedding", sa.Column("atom_version", sa.Integer(), nullable=True))
    op.add_column("atom_embedding", sa.Column("content_hash", sa.String(), nullable=True))
    op.add_column("atom_embedding", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("atom_embedding", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("atom_embedding", "updated_at")
    op.drop_column("atom_embedding", "last_error")
    op.drop_column("atom_embedding", "content_hash")
    op.drop_column("atom_embedding", "atom_version")
