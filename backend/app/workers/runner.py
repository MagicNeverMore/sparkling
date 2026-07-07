"""后台 worker：轮询 task_queue，处理 embed、link_discover 和 trend_collect 任务。"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import anyio

from ..db import SessionLocal
from ..logger import get_logger
from ..models import Settings, TaskQueue, TrendRun
from ..services.memory.cleanup import purge_expired_deleted_atoms
from ..services import task_queue as tq
from ..services.memory.embedding import mark_atom_embedding_error, sync_atom_embedding
from ..services.memory.linker import discover_links
from ..services.settings.settings_snapshot import (
    EmbeddingSettingsSnapshot,
    LinkSettingsSnapshot,
    snapshot_embedding_settings,
    snapshot_link_settings,
)
from ..services.trend.collector import collect_trends, maybe_enqueue_due_trend_run
from ..services.ws_manager import manager

logger = get_logger(__name__)

# 无新任务时的兜底轮询间隔（秒），防止 wakeup event 丢失
POLL_INTERVAL = 30.0
CLEANUP_INTERVAL = timedelta(hours=24)
TREND_SCHEDULER_INTERVAL = timedelta(minutes=1)
GLOBAL_CONCURRENCY_LIMIT = 3
TASK_TYPE_CONCURRENCY_LIMITS = {
    "embed": 2,
    "link_discover": 1,
    "trend_collect": 1,
}
TASK_TIMEOUT_SECONDS = {
    "embed": 180,
    "link_discover": 60,
    "trend_collect": 1800,
}
TASK_LEASE_GRACE_SECONDS = 60
SETTINGS_NOT_READY_RETRY_SECONDS = 30


@dataclass(frozen=True)
class _ClaimedTask:
    id: str
    task_type: str
    payload: dict


@dataclass(frozen=True)
class _WorkerSettings:
    embedding: EmbeddingSettingsSnapshot
    link: LinkSettingsSnapshot


async def _handle_embed(payload: dict, settings: EmbeddingSettingsSnapshot) -> None:
    """处理 embed 任务：生成向量 → 写 vec_atoms → 入队 link_discover。"""
    atom_id = payload.get("atom_id")
    if not atom_id:
        raise ValueError("embed 任务缺少 atom_id")
    embedded = await sync_atom_embedding(
        atom_id,
        settings,
        expected_version=payload.get("atom_version"),
    )
    if not embedded:
        logger.info("embed 已跳过，atom_id=%s", atom_id)
        return
    # embed 完成后立即触发关联发现
    with SessionLocal() as session:
        tq.enqueue(session, "link_discover", {"atom_id": atom_id, "atom_version": payload.get("atom_version")})
    logger.info("embed 完成，已入队 link_discover，atom_id=%s", atom_id)


async def _handle_link_discover(payload: dict, settings: LinkSettingsSnapshot) -> None:
    """处理 link_discover 任务：KNN 发现语义关联 → 写 DB → 广播给前端。"""
    atom_id = payload.get("atom_id")
    if not atom_id:
        raise ValueError("link_discover 任务缺少 atom_id")
    links = await discover_links(
        atom_id,
        settings,
        manager,
        expected_version=payload.get("atom_version"),
    )
    logger.info("link_discover 完成，atom_id=%s，发现关联 %d 条", atom_id, len(links))


async def _handle_trend_collect(payload: dict) -> None:
    """处理 Trend 采集任务：source discovery → WebFetch → LLM 评分 → 入库。"""
    run_id = payload.get("run_id")
    if not run_id:
        raise ValueError("trend_collect 任务缺少 run_id")
    result = await collect_trends(run_id)
    logger.info(
        "trend_collect 完成，run_id=%s，候选 %d 条，入库 %d 条",
        run_id,
        result["candidate_count"],
        result["saved_count"],
    )


_HANDLERS = {
    "embed": _handle_embed,
    "link_discover": _handle_link_discover,
    "trend_collect": _handle_trend_collect,
}


def _claim_task(
    *,
    worker_id: str,
    blocked_task_types: set[str] | None = None,
    excluded_task_ids: set[str] | None = None,
) -> _ClaimedTask | None:
    with SessionLocal() as session:
        task = tq.claim_next(
            session,
            worker_id=worker_id,
            lease_seconds=_task_lease_seconds("unknown"),
            lease_seconds_by_type={
                task_type: _task_lease_seconds(task_type)
                for task_type in TASK_TIMEOUT_SECONDS
            },
            blocked_task_types=blocked_task_types,
            excluded_task_ids=excluded_task_ids,
        )
        if task is None:
            return None
        try:
            payload = json.loads(task.payload or "{}")
        except json.JSONDecodeError as exc:
            tq.mark_failed(session, task.id, f"任务 payload JSON 无效: {exc}")
            return None
        return _ClaimedTask(
            id=task.id,
            task_type=task.task_type,
            payload=payload,
        )


def _load_worker_settings() -> _WorkerSettings | None:
    with SessionLocal() as session:
        settings = session.get(Settings, 1)
        if settings is None or not settings.embed_model or not settings.embed_dim:
            return None
        return _WorkerSettings(
            embedding=snapshot_embedding_settings(settings),
            link=snapshot_link_settings(settings),
        )


def _defer_task_until_settings_ready(task_id: str) -> None:
    with SessionLocal() as session:
        task = session.get(TaskQueue, task_id)
        if task is None:
            return
        now = datetime.utcnow()
        task.status = "pending"
        task.attempts = max(0, task.attempts - 1)
        task.available_at = now + timedelta(seconds=SETTINGS_NOT_READY_RETRY_SECONDS)
        task.locked_by = None
        task.locked_at = None
        task.lease_until = None
        task.updated_at = now
        session.commit()


def _mark_task_done(task_id: str) -> None:
    with SessionLocal() as session:
        tq.mark_done(session, task_id)


def _mark_task_failed(task: _ClaimedTask, exc: Exception) -> None:
    with SessionLocal() as session:
        if task.task_type == "embed" and task.payload.get("atom_id"):
            mark_atom_embedding_error(session, task.payload["atom_id"], str(exc))
        status = tq.mark_failed(session, task.id, str(exc))
        _sync_trend_run_after_task_failure(session, task, str(exc), status)


def _mark_task_released(task: _ClaimedTask, reason: str) -> None:
    with SessionLocal() as session:
        tq.release_running(session, task.id, reason)
        _sync_trend_run_after_task_failure(session, task, reason, "pending")


def _sync_trend_run_after_task_failure(
    session,  # noqa: ANN001
    task: _ClaimedTask,
    error: str,
    task_status: str | None,
) -> None:
    if task.task_type != "trend_collect":
        return
    run_id = task.payload.get("run_id")
    if not run_id:
        return
    run = session.get(TrendRun, run_id)
    if run is None:
        return
    now = datetime.utcnow()
    if task_status == "failed":
        run.status = "failed"
        run.finished_at = now
    else:
        run.status = "pending"
    run.error = error[:2000]
    run.updated_at = now
    session.commit()


async def _execute_claimed_task(task: _ClaimedTask) -> bool:
    handler = _HANDLERS.get(task.task_type)
    if handler is None:
        raise ValueError(f"未知任务类型: {task.task_type}")

    settings = None
    if task.task_type in {"embed", "link_discover"}:
        settings = _load_worker_settings()
        if settings is None:
            _defer_task_until_settings_ready(task.id)
            logger.debug("Settings 未配置，任务 %s 本轮跳过", task.id)
            return False

    if task.task_type == "embed" and settings is not None:
        await _handle_embed(task.payload, settings.embedding)
    elif task.task_type == "link_discover" and settings is not None:
        await _handle_link_discover(task.payload, settings.link)
    elif task.task_type == "trend_collect":
        await _handle_trend_collect(task.payload)
    return True


async def _run_claimed_task(task: _ClaimedTask) -> None:
    cancelled_exc = anyio.get_cancelled_exc_class()
    timeout_seconds = _task_timeout_seconds(task.task_type)
    try:
        with anyio.fail_after(timeout_seconds):
            completed = await _execute_claimed_task(task)
        if completed:
            _mark_task_done(task.id)
    except TimeoutError:
        message = f"任务执行超时（>{timeout_seconds}s）"
        logger.warning("任务 %s 超时: %s", task.id, message)
        _mark_task_failed(task, TimeoutError(message))
    except cancelled_exc:
        _mark_task_released(task, "worker cancelled")
        raise
    except Exception as exc:
        logger.exception("任务 %s 执行失败: %s", task.id, exc)
        _mark_task_failed(task, exc)


async def _drain_pending_tasks_once(worker_id: str | None = None) -> int:
    """消费当前可处理任务；配置未就绪的 AI 任务只跳过本轮，不能阻塞 Trend。"""
    worker_id = worker_id or _worker_id()
    deferred_until_settings_ready: set[str] = set()
    processed = 0
    while True:
        task = _claim_task(worker_id=worker_id, excluded_task_ids=deferred_until_settings_ready)
        if task is None:
            break
        await _run_claimed_task(task)
        with SessionLocal() as session:
            current = session.get(TaskQueue, task.id)
            if current is not None and current.status == "pending":
                deferred_until_settings_ready.add(task.id)
            else:
                processed += 1
    return processed


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"


def _task_timeout_seconds(task_type: str) -> int:
    return TASK_TIMEOUT_SECONDS.get(task_type, 120)


def _task_lease_seconds(task_type: str) -> int:
    return _task_timeout_seconds(task_type) + TASK_LEASE_GRACE_SECONDS


def _blocked_task_types(active_counts: dict[str, int]) -> set[str]:
    blocked = set()
    for task_type, limit in TASK_TYPE_CONCURRENCY_LIMITS.items():
        if active_counts.get(task_type, 0) >= limit:
            blocked.add(task_type)
    return blocked


def _reclaim_expired_task_leases() -> int:
    with SessionLocal() as session:
        return tq.reclaim_expired_leases(session)


async def _start_available_tasks(
    task_group: anyio.abc.TaskGroup,
    *,
    worker_id: str,
    active_counts: dict[str, int],
    active_task_ids: set[str],
    event: asyncio.Event,
) -> int:
    started = 0
    while len(active_task_ids) < GLOBAL_CONCURRENCY_LIMIT:
        task = _claim_task(
            worker_id=worker_id,
            blocked_task_types=_blocked_task_types(active_counts),
        )
        if task is None:
            break
        active_task_ids.add(task.id)
        active_counts[task.task_type] = active_counts.get(task.task_type, 0) + 1
        task_group.start_soon(_run_and_track_task, task, active_counts, active_task_ids, event)
        started += 1
    return started


async def _run_and_track_task(
    task: _ClaimedTask,
    active_counts: dict[str, int],
    active_task_ids: set[str],
    event: asyncio.Event,
) -> None:
    try:
        await _run_claimed_task(task)
    finally:
        active_task_ids.discard(task.id)
        active_counts[task.task_type] = max(0, active_counts.get(task.task_type, 1) - 1)
        event.set()


async def _worker_loop() -> None:
    """
    后台任务主循环：
    - 等待 wakeup event 或超时（防止信号丢失导致任务堆积）
    - 持续消费 pending 任务直到队列为空
    - 任务失败自动重试，超过上限标记 failed
    - Settings 未配置时保持任务 pending，等用户配置后下次唤醒处理
    """
    event = tq.get_wakeup_event()
    worker_id = _worker_id()
    logger.info("Sparkling worker 已启动 worker_id=%s", worker_id)
    last_cleanup_at: datetime | None = None
    last_trend_schedule_check_at: datetime | None = None
    active_counts: dict[str, int] = {}
    active_task_ids: set[str] = set()

    async with anyio.create_task_group() as task_group:
        while True:
            now = datetime.utcnow()
            if last_cleanup_at is None or now - last_cleanup_at >= CLEANUP_INTERVAL:
                with SessionLocal() as session:
                    purge_expired_deleted_atoms(session)
                last_cleanup_at = now

            reclaimed = _reclaim_expired_task_leases()
            if reclaimed:
                logger.info("已回收过期任务租约 %d 条", reclaimed)

            if last_trend_schedule_check_at is None or now - last_trend_schedule_check_at >= TREND_SCHEDULER_INTERVAL:
                with SessionLocal() as session:
                    settings = session.get(Settings, 1)
                    if settings is not None:
                        run = maybe_enqueue_due_trend_run(session, settings, now)
                        if run is not None:
                            logger.info("Trend 定时任务已入队，run_id=%s", run.id)
                last_trend_schedule_check_at = now

            started = await _start_available_tasks(
                task_group,
                worker_id=worker_id,
                active_counts=active_counts,
                active_task_ids=active_task_ids,
                event=event,
            )
            if started:
                continue

            try:
                await asyncio.wait_for(event.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass
            event.clear()


async def start_worker() -> asyncio.Task:
    return asyncio.create_task(_worker_loop(), name="sparkling-worker")


async def stop_worker(task: Optional[asyncio.Task]) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Sparkling worker 已停止")
