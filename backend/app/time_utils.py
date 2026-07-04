"""Datetime helpers for API serialization.

Database datetimes are stored as UTC. SQLite returns them as naive datetime
objects, so API responses must mark them as UTC explicitly.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_isoformat(value: datetime) -> str:
    """Serialize a database datetime as an explicit UTC ISO timestamp."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
