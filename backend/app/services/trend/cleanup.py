"""Trend 软删除数据的定期清理。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...logger import get_logger
from ...models import TrendItem

logger = get_logger(__name__)

TREND_SOFT_DELETE_RETENTION_DAYS = 30
TREND_AUTO_DELETE_DAYS = 60


def soft_delete_stale_unfavorited_trends(session: Session, now: datetime | None = None) -> int:
    """软删除超过 60 天未更新、且未收藏的 Trend。"""
    current_time = now or datetime.utcnow()
    cutoff = current_time - timedelta(days=TREND_AUTO_DELETE_DAYS)
    stale = (
        session.query(TrendItem)
        .filter(TrendItem.deleted_at.is_(None))
        .filter(TrendItem.last_seen_at < cutoff)
    )
    scanned_count = stale.count()
    favorited_skipped = stale.filter(TrendItem.is_favorited.is_(True)).count()
    deleted_count = (
        stale.filter(TrendItem.is_favorited.is_(False))
        .update(
            {TrendItem.deleted_at: current_time, TrendItem.updated_at: current_time},
            synchronize_session=False,
        )
    )
    session.commit()
    logger.info(
        "Trend 自动清理完成 scanned=%d soft_deleted=%d favorited_skipped=%d retention_days=%d",
        scanned_count,
        deleted_count,
        favorited_skipped,
        TREND_AUTO_DELETE_DAYS,
    )
    return deleted_count


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
