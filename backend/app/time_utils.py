"""Datetime helpers for API serialization.

Database datetimes are stored as UTC. SQLite returns them as naive datetime
objects, so API responses must mark them as UTC explicitly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .logger import get_logger


DEFAULT_TIMEZONE = "UTC"
logger = get_logger(__name__)


def utc_isoformat(value: datetime) -> str:
    """Serialize a database datetime as an explicit UTC ISO timestamp."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def get_timezone(value: str | None) -> ZoneInfo:
    """Return a validated IANA timezone, falling back to UTC for empty values."""
    name = value or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        logger.warning("无效 timezone value=%s", name)
        raise ValueError(f"Invalid timezone: {name}") from exc


def utc_naive_to_local(value: datetime, timezone_name: str | None) -> datetime:
    """Interpret a database datetime as UTC and convert it to a local aware datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.astimezone(get_timezone(timezone_name))


def local_to_utc_naive(value: datetime) -> datetime:
    """Convert a local aware datetime to the naive UTC format used by the database."""
    if value.tzinfo is None:
        msg = "local_to_utc_naive requires an aware datetime"
        logger.warning("本地时间转换失败：datetime 缺少 tzinfo")
        raise ValueError(msg)
    return value.astimezone(timezone.utc).replace(tzinfo=None)
