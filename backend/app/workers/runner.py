"""后台 worker：轮询 task_queue，处理 embed、link_discover 和 trend_collect 任务。"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..db import SessionLocal
from ..logger import get_logger
from ..models import Settings, TaskQueue
from ..services.cleanup import purge_expired_deleted_atoms
from ..services import task_queue as tq
from ..services.embedding import mark_atom_embedding_error, sync_atom_embedding
from ..services.linker import discover_links
from ..services.settings_snapshot import (
    EmbeddingSettingsSnapshot,
    LinkSettingsSnapshot,
    snapshot_embedding_settings,
    snapshot_link_settings,
)
from ..services.trend.collector import collect_trends, maybe_enqueue_due_trend_run
from ..services.ws_manager import manager

logger = get_logger(__name__)

MAX_ATTEMPTS = 3
# 无新任务时的兜底轮询间隔（秒），防止 wakeup event 丢失
POLL_INTERVAL = 30.0
CLEANUP_INTERVAL = timedelta(hours=24)
TREND_SCHEDULER_INTERVAL = timedelta(minutes=1)


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


def _claim_task() -> _ClaimedTask | None:
    with SessionLocal() as session:
        task = tq.claim_next(session)
        if task is None:
            return None
        return _ClaimedTask(
            id=task.id,
            task_type=task.task_type,
            payload=json.loads(task.payload or "{}"),
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
        task.status = "pending"
        task.attempts = max(0, task.attempts - 1)
        session.commit()


def _mark_task_done(task_id: str) -> None:
    with SessionLocal() as session:
        tq.mark_done(session, task_id)


def _mark_task_failed(task: _ClaimedTask, exc: Exception) -> None:
    with SessionLocal() as session:
        if task.task_type == "embed" and task.payload.get("atom_id"):
            mark_atom_embedding_error(session, task.payload["atom_id"], str(exc))
        tq.mark_failed(session, task.id, str(exc), MAX_ATTEMPTS)


async def _worker_loop() -> None:
    """
    后台任务主循环：
    - 等待 wakeup event 或超时（防止信号丢失导致任务堆积）
    - 持续消费 pending 任务直到队列为空
    - 任务失败自动重试，超过上限标记 failed
    - Settings 未配置时保持任务 pending，等用户配置后下次唤醒处理
    """
    event = tq.get_wakeup_event()
    logger.info("Sparkling worker 已启动")
    last_cleanup_at: datetime | None = None
    last_trend_schedule_check_at: datetime | None = None

    while True:
        now = datetime.utcnow()
        if last_cleanup_at is None or now - last_cleanup_at >= CLEANUP_INTERVAL:
            with SessionLocal() as session:
                purge_expired_deleted_atoms(session)
            last_cleanup_at = now

        if last_trend_schedule_check_at is None or now - last_trend_schedule_check_at >= TREND_SCHEDULER_INTERVAL:
            with SessionLocal() as session:
                settings = session.get(Settings, 1)
                if settings is not None:
                    run = maybe_enqueue_due_trend_run(session, settings, now)
                    if run is not None:
                        logger.info("Trend 定时任务已入队，run_id=%s", run.id)
            last_trend_schedule_check_at = now

        try:
            await asyncio.wait_for(event.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass
        event.clear()

        # 持续消费，直到队列空
        while True:
            task = _claim_task()
            if task is None:
                break

            handler = _HANDLERS.get(task.task_type)
            if handler is None:
                with SessionLocal() as session:
                    tq.mark_failed(session, task.id, f"未知任务类型: {task.task_type}", MAX_ATTEMPTS)
                continue

            settings = None
            if task.task_type in {"embed", "link_discover"}:
                # 每次任务都重新读 settings，支持热更新 AI provider 配置。
                # 只保留不可变快照，外部 API 调用期间不持有数据库 Session。
                settings = _load_worker_settings()
                if settings is None:
                    _defer_task_until_settings_ready(task.id)
                    logger.debug("Settings 未配置，任务 %s 保持 pending", task.id)
                    break

            try:
                if task.task_type == "embed" and settings is not None:
                    await _handle_embed(task.payload, settings.embedding)
                elif task.task_type == "link_discover" and settings is not None:
                    await _handle_link_discover(task.payload, settings.link)
                elif task.task_type == "trend_collect":
                    await _handle_trend_collect(task.payload)
                _mark_task_done(task.id)
            except Exception as exc:
                logger.exception("任务 %s 执行失败: %s", task.id, exc)
                _mark_task_failed(task, exc)


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
