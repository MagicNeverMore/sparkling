"""merge trend timezone and task queue lease heads

Revision ID: b8c0d1e2f3a4
Revises: a7b8c9d0e1f2, a7b9c1d2e3f4
Create Date: 2026-07-07 10:20:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "b8c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = ("a7b8c9d0e1f2", "a7b9c1d2e3f4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge-only revision; schema changes are in both parent revisions."""


def downgrade() -> None:
    """Merge-only revision; parent downgrades handle schema changes."""
