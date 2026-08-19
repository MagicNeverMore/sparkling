"""Social Media 日级采集调度与完整数据集原子发布。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ...db import SessionLocal
from ...models import (
    SocialMediaDataset,
    SocialMediaSyncRun,
    SocialMediaVideoSnapshot,
    TaskQueue,
)
from ...time_utils import get_timezone, local_to_utc_naive, utc_isoformat, utc_naive_to_local
from .. import task_queue as tq
from .config import load_social_media_config, update_social_media_config
from .youtube import fetch_daily_dataset


def enqueue_social_media_run(session: Session, trigger: str = "manual") -> SocialMediaSyncRun:
    active = (
        session.query(SocialMediaSyncRun)
        .filter(SocialMediaSyncRun.status.in_(["pending", "running"]))
        .order_by(SocialMediaSyncRun.created_at.desc())
        .first()
    )
    if active is not None:
        return active
    config = load_social_media_config()
    run = SocialMediaSyncRun(
        platform="youtube",
        external_account_id=config.youtube_channel_id,
        trigger=trigger,
        status="pending",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    tq.enqueue(
        session,
        "social_media_collect",
        {"run_id": run.id},
        resource_key="social_media:youtube",
    )
    return run


def maybe_enqueue_due_social_media_run(
    session: Session,
    now: datetime | None = None,
) -> SocialMediaSyncRun | None:
    now = now or datetime.utcnow()
    config = load_social_media_config()
    if not config.schedule_enabled or config.update_frequency == "manual" or not config.youtube_connected:
        return None
    next_run = _parse_utc(config.next_run_at)
    if next_run is None:
        next_run = calculate_next_run_at(config.update_frequency, config.schedule_time, config.timezone, now)
        update_social_media_config(next_run_at=utc_isoformat(next_run))
        return None
    if next_run > now:
        return None
    active_task = (
        session.query(TaskQueue)
        .filter(TaskQueue.task_type == "social_media_collect")
        .filter(TaskQueue.status.in_(["pending", "running"]))
        .first()
    )
    active_run = (
        session.query(SocialMediaSyncRun)
        .filter(SocialMediaSyncRun.status.in_(["pending", "running"]))
        .first()
    )
    if active_task or active_run:
        return None
    update_social_media_config(
        next_run_at=utc_isoformat(
            calculate_next_run_at(config.update_frequency, config.schedule_time, config.timezone, now)
        )
    )
    return enqueue_social_media_run(session, "scheduled")


def calculate_next_run_at(
    frequency: str,
    schedule_time: str,
    timezone_name: str,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.utcnow()
    local_now = utc_naive_to_local(now, timezone_name)
    try:
        hour, minute = (int(part) for part in schedule_time.split(":"))
    except (TypeError, ValueError):
        hour, minute = 9, 0
    get_timezone(timezone_name)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=7 if frequency == "weekly" else 1)
    return local_to_utc_naive(candidate)


async def collect_social_media(run_id: str) -> dict[str, int | str]:
    with SessionLocal() as session:
        run = session.get(SocialMediaSyncRun, run_id)
        if run is None:
            raise ValueError("Social Media sync run 不存在")
        run.status = "running"
        run.started_at = datetime.utcnow()
        run.error = None
        session.commit()

    config = load_social_media_config()
    dataset = await fetch_daily_dataset(config)
    collected_at = datetime.utcnow()

    with SessionLocal() as session:
        # (platform, account, metric_date) 唯一；同日重跑整批替换，不产生重复指标行。
        stored = (
            session.query(SocialMediaDataset)
            .filter(SocialMediaDataset.platform == "youtube")
            .filter(SocialMediaDataset.external_account_id == dataset.channel_id)
            .filter(SocialMediaDataset.metric_date == dataset.metric_date)
            .one_or_none()
        )
        if stored is None:
            stored = SocialMediaDataset(
                platform="youtube",
                external_account_id=dataset.channel_id,
                metric_date=dataset.metric_date,
                status="complete",
                collected_at=collected_at,
            )
            session.add(stored)
            session.flush()
        else:
            session.query(SocialMediaVideoSnapshot).filter(
                SocialMediaVideoSnapshot.dataset_id == stored.id
            ).delete(synchronize_session=False)
            stored.status = "complete"
            stored.collected_at = collected_at
            stored.updated_at = collected_at

        for video in dataset.videos:
            metrics = dataset.metrics_by_video[video.video_id]
            session.add(
                SocialMediaVideoSnapshot(
                    dataset_id=stored.id,
                    external_video_id=video.video_id,
                    title=video.title,
                    published_at=video.published_at,
                    duration_seconds=video.duration_seconds,
                    views=metrics.views,
                    ctr=metrics.ctr,
                    average_view_duration_seconds=metrics.average_view_duration_seconds,
                    average_view_percentage=metrics.average_view_percentage,
                    subscribers_gained=metrics.subscribers_gained,
                    subscribers_lost=metrics.subscribers_lost,
                    net_subscribers=metrics.subscribers_gained - metrics.subscribers_lost,
                )
            )

        run = session.get(SocialMediaSyncRun, run_id)
        if run is None:
            raise ValueError("Social Media sync run 不存在")
        run.external_account_id = dataset.channel_id
        run.metric_date = dataset.metric_date
        run.video_count = len(dataset.videos)
        run.status = "done"
        run.finished_at = collected_at
        run.updated_at = collected_at
        session.commit()

    current = load_social_media_config()
    update_social_media_config(
        youtube_channel_id=dataset.channel_id,
        youtube_channel_title=dataset.channel_title,
        last_run_at=utc_isoformat(collected_at),
        next_run_at=(
            utc_isoformat(
                calculate_next_run_at(
                    current.update_frequency,
                    current.schedule_time,
                    current.timezone,
                    collected_at,
                )
            )
            if current.schedule_enabled and current.update_frequency != "manual"
            else None
        ),
    )
    return {"metric_date": dataset.metric_date, "video_count": len(dataset.videos)}


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=None)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc).replace(tzinfo=None)
    )
