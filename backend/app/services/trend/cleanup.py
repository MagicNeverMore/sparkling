"""Trend 软删除数据的定期清理。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...logger import get_logger
from ...models import TrendItem

logger = get_logger(__name__)

TREND_SOFT_DELETE_RETENTION_DAYS = 30


def purge_expired_deleted_trends(session: Session, now: datetime | None = None) -> int:
    """硬删除已软删除超过 30 天的热点。"""
    cutoff = (now or datetime.utcnow()) - timedelta(days=TREND_SOFT_DELETE_RETENTION_DAYS)
    deleted_count = (
        session.query(TrendItem)
        .filter(TrendItem.deleted_at.is_not(None))
        .filter(TrendItem.deleted_at < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    if deleted_count:
        logger.info(
            "已硬删除 %d 条超过 %d 天的软删除 Trend",
            deleted_count,
            TREND_SOFT_DELETE_RETENTION_DAYS,
        )
    return deleted_count
