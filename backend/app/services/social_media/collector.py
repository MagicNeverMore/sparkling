"""Social Media 小时采集调度与完整数据集原子发布。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...db import SessionLocal
from ...logger import get_logger
from ...models import (
    SocialMediaSyncRun,
    SocialMediaVideo,
    SocialMediaVideoMetric,
    TaskQueue,
)
from ...time_utils import utc_isoformat
from .. import task_queue as tq
from .config import load_social_media_config, update_social_media_config
from .youtube import fetch_daily_dataset

logger = get_logger(__name__)

# 社交媒体同步只涉及有限数量的 API 请求；超过该时长可明确判定异常，
# 绝不能让 UI 长期保留“同步中”。
SOCIAL_MEDIA_RUN_TIMEOUT_SECONDS = 180


def _get_or_recover_sync_run(
    session: Session,
    run_id: str,
    *,
    phase: str,
) -> SocialMediaSyncRun:
    """恢复历史遗留或热切库产生的孤儿采集任务。"""
    run = session.get(SocialMediaSyncRun, run_id)
    if run is not None:
        return run

    run = SocialMediaSyncRun(
        id=run_id,
        platform="youtube",
        trigger="recovered",
        status="running",
    )
    session.add(run)
    session.flush()
    logger.warning(
        "social_media.sync.run_recovered run_id=%s phase=%s reason=orphan_task",
        run_id,
        phase,
    )
    return run


def enqueue_social_media_task(session: Session, trigger: str = "manual") -> TaskQueue:
    """提交独立采集任务；run 由 worker 真正开始执行时创建。"""
    if trigger not in {"manual", "scheduled"}:
        raise ValueError(f"不支持的 Social Media task trigger: {trigger}")
    dedupe_key = f"social_media:{trigger}"
    active = (
        session.query(TaskQueue)
        .filter(TaskQueue.dedupe_key == dedupe_key)
        .filter(TaskQueue.status.in_(["pending", "running"]))
        .order_by(TaskQueue.created_at.desc())
        .first()
    )
    if active is not None:
        logger.info(
            "social_media.sync.task_reused task_id=%s trigger=%s status=%s",
            active.id,
            trigger,
            active.status,
        )
        return active

    try:
        task = tq.enqueue(
            session,
            "social_media_collect",
            {"trigger": trigger},
            priority=100 if trigger == "manual" else 0,
            resource_key="social_media:youtube",
            dedupe_key=dedupe_key,
            max_attempts=1,
        )
    except IntegrityError:
        # 并发请求由数据库唯一索引裁决；失败方返回获胜的 active task。
        session.rollback()
        task = (
            session.query(TaskQueue)
            .filter(TaskQueue.dedupe_key == dedupe_key)
            .order_by(TaskQueue.created_at.desc())
            .first()
        )
        if task is None:
            raise RuntimeError(f"并发去重冲突后未找到获胜 task: {dedupe_key}")
        logger.info(
            "social_media.sync.task_reused_after_conflict task_id=%s trigger=%s status=%s",
            task.id,
            trigger,
            task.status,
        )
        return task
    logger.info(
        "social_media.sync.task_enqueued task_id=%s trigger=%s priority=%s",
        task.id,
        trigger,
        task.priority,
    )
    return task


def start_social_media_run(
    session: Session,
    trigger: str,
    run_id: str | None = None,
) -> SocialMediaSyncRun:
    """在调用方 transaction 内创建 running run；兼容引用旧 run_id 的历史 task。"""
    if run_id:
        legacy_run = session.get(SocialMediaSyncRun, run_id)
        if legacy_run is not None and legacy_run.status in {"done", "failed"}:
            run = SocialMediaSyncRun(
                platform="youtube",
                trigger=(
                    legacy_run.trigger
                    if legacy_run.trigger in {"manual", "scheduled"}
                    else trigger
                ),
                status="running",
            )
            session.add(run)
            session.flush()
            logger.warning(
                "social_media.sync.legacy_terminal_run_replaced old_run_id=%s "
                "new_run_id=%s old_status=%s",
                run_id,
                run.id,
                legacy_run.status,
            )
        else:
            run = _get_or_recover_sync_run(session, run_id, phase="start")
    else:
        run = SocialMediaSyncRun(
            platform="youtube",
            trigger=trigger,
            status="running",
        )
        session.add(run)
        session.flush()
    run.status = "running"
    run.started_at = datetime.utcnow()
    run.finished_at = None
    run.error = None
    return run


def maybe_enqueue_due_social_media_task(
    session: Session,
    now: datetime | None = None,
) -> TaskQueue | None:
    now = now or datetime.utcnow()
    config = load_social_media_config()
    if not config.schedule_enabled or config.update_frequency == "manual" or not config.youtube_connected:
        return None
    next_run = _parse_utc(config.next_run_at)
    if next_run is None:
        next_run = calculate_next_run_at(config.update_frequency, config.schedule_time, config.timezone, now)
        update_social_media_config(next_run_at=utc_isoformat(next_run))
        logger.info("social_media.schedule.initialized next_run_at=%s", utc_isoformat(next_run))
        return None
    if next_run > now:
        return None
    update_social_media_config(
        next_run_at=utc_isoformat(
            calculate_next_run_at(config.update_frequency, config.schedule_time, config.timezone, now)
        )
    )
    task = enqueue_social_media_task(session, "scheduled")
    logger.info(
        "social_media.schedule.hourly_enqueued task_id=%s scheduled_at=%s",
        task.id,
        utc_isoformat(now),
    )
    return task


def calculate_next_run_at(
    frequency: str,
    schedule_time: str,
    timezone_name: str,
    now: datetime | None = None,
) -> datetime:
    """计算下一次小时快照查询时间。"""
    now = now or datetime.utcnow()
    if frequency != "hourly":
        logger.warning(
            "social_media.schedule.legacy_frequency normalized_to_hourly frequency=%s",
            frequency,
        )
    return now + timedelta(hours=1)


async def collect_social_media(run_id: str) -> dict[str, int | str]:
    logger.info("social_media.sync.start run_id=%s", run_id)
    config = load_social_media_config()
    dataset = await fetch_daily_dataset(config)
    collected_at = datetime.utcnow()
    daily_metrics = dataset.daily_metrics()
    if not daily_metrics:
        raise ValueError("YouTube 在最近十天内没有可写入的视频分析数据")
    logger.info(
        "social_media.sync.dataset_ready run_id=%s channel_id=%s latest_data_date=%s videos=%s data_dates=%s",
        run_id,
        dataset.channel_id,
        dataset.metric_date,
        len(dataset.videos),
        sorted(daily_metrics),
    )

    with SessionLocal() as session:
        videos_by_external_id: dict[str, SocialMediaVideo] = {}
        base_modes: list[str] = []
        for video in dataset.videos:
            stored_video = (
                session.query(SocialMediaVideo)
                .filter_by(platform="youtube", external_video_id=video.video_id)
                .one_or_none()
            )
            if stored_video is None:
                stored_video = SocialMediaVideo(
                    platform="youtube",
                    external_account_id=dataset.channel_id,
                    external_video_id=video.video_id,
                    title=video.title,
                    published_at=video.published_at,
                    duration_seconds=video.duration_seconds,
                )
                session.add(stored_video)
                session.flush()
                base_modes.append("insert")
            else:
                stored_video.external_account_id = dataset.channel_id
                stored_video.title = video.title
                stored_video.published_at = video.published_at
                stored_video.duration_seconds = video.duration_seconds
                stored_video.updated_at = collected_at
                base_modes.append("upsert")
            videos_by_external_id[video.video_id] = stored_video

        published: list[tuple[str, int, int]] = []
        for data_date, metrics_by_video in daily_metrics.items():
            inserted = 0
            updated = 0
            for external_video_id, metrics in metrics_by_video.items():
                video = videos_by_external_id[external_video_id]
                stored_metric = (
                    session.query(SocialMediaVideoMetric)
                    .filter_by(video_id=video.id, data_date=data_date)
                    .one_or_none()
                )
                values = dict(
                    views=metrics.views, ctr=metrics.ctr,
                    average_view_duration_seconds=metrics.average_view_duration_seconds,
                    average_view_percentage=metrics.average_view_percentage,
                    subscribers_gained=metrics.subscribers_gained,
                    subscribers_lost=metrics.subscribers_lost,
                    net_subscribers=metrics.subscribers_gained - metrics.subscribers_lost,
                )
                if stored_metric is None:
                    session.add(SocialMediaVideoMetric(
                        video_id=video.id, data_date=data_date, **values
                    ))
                    inserted += 1
                else:
                    for field, value in values.items():
                        setattr(stored_metric, field, value)
                    stored_metric.updated_at = collected_at
                    updated += 1
            published.append((data_date, inserted, updated))

        run = _get_or_recover_sync_run(session, run_id, phase="publish")
        if run.status != "running":
            # API 调用在线程中执行；即使超时后线程晚到，也不得把已失败的 run
            # 覆盖回 done，更不能发布过期结果。
            raise RuntimeError(f"Social Media sync run 已终结，拒绝发布结果: {run.status}")
        run.external_account_id = dataset.channel_id
        run.metric_date = dataset.metric_date
        run.video_count = len(dataset.videos)
        run.status = "done"
        run.finished_at = collected_at
        run.updated_at = collected_at
        session.commit()
        logger.info(
            "social_media.sync.persisted run_id=%s base_videos=%s data_dates=%s latest_data_date=%s videos=%s",
            run_id, {mode: base_modes.count(mode) for mode in set(base_modes)}, published, dataset.metric_date,
            len(dataset.videos),
        )

    update_social_media_config(
        youtube_channel_id=dataset.channel_id,
        youtube_channel_title=dataset.channel_title,
        last_run_at=utc_isoformat(collected_at),
    )
    logger.info(
        "social_media.sync.done run_id=%s metric_date=%s videos=%s collected_at=%s",
        run_id,
        dataset.metric_date,
        len(dataset.videos),
        utc_isoformat(collected_at),
    )
    return {
        "metric_date": dataset.metric_date,
        "video_count": len(dataset.videos),
    }


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=None)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc).replace(tzinfo=None)
    )
