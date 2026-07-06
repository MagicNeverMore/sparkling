"""后台 worker：轮询 task_queue，处理 embed 和 link_discover 任务。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional

from ..db import SessionLocal
from ..logger import get_logger
from ..models import Settings
from ..services.cleanup import purge_expired_deleted_atoms
from ..services import task_queue as tq
from ..services.embedding import mark_atom_embedding_error, sync_atom_embedding
from ..services.linker import discover_links
from ..services.trend.collector import collect_trends, maybe_enqueue_due_trend_run
from ..services.ws_manager import manager

logger = get_logger(__name__)

MAX_ATTEMPTS = 3
# 无新任务时的兜底轮询间隔（秒），防止 wakeup event 丢失
POLL_INTERVAL = 30.0
CLEANUP_INTERVAL = timedelta(hours=24)
TREND_SCHEDULER_INTERVAL = timedelta(minutes=1)


async def _handle_embed(session, payload: dict, settings: Settings) -> None:
    """处理 embed 任务：生成向量 → 写 vec_atoms → 入队 link_discover。"""
    atom_id = payload.get("atom_id")
    if not atom_id:
        raise ValueError("embed 任务缺少 atom_id")
    embedded = await sync_atom_embedding(
        session,
        atom_id,
        settings,
        expected_version=payload.get("atom_version"),
    )
    if not embedded:
        logger.info("embed 已跳过，atom_id=%s", atom_id)
        return
    # embed 完成后立即触发关联发现
    tq.enqueue(session, "link_discover", {"atom_id": atom_id, "atom_version": payload.get("atom_version")})
    logger.info("embed 完成，已入队 link_discover，atom_id=%s", atom_id)


async def _handle_link_discover(session, payload: dict, settings: Settings) -> None:
    """处理 link_discover 任务：KNN 发现语义关联 → 写 DB → 广播给前端。"""
    atom_id = payload.get("atom_id")
    if not atom_id:
        raise ValueError("link_discover 任务缺少 atom_id")
    links = await discover_links(
        session,
        atom_id,
        settings,
        manager,
        expected_version=payload.get("atom_version"),
    )
    logger.info("link_discover 完成，atom_id=%s，发现关联 %d 条", atom_id, len(links))


async def _handle_trend_collect(session, payload: dict, _settings: Settings | None) -> None:
    """处理 Trend 采集任务：source discovery → WebFetch → LLM 评分 → 入库。"""
    run_id = payload.get("run_id")
    if not run_id:
        raise ValueError("trend_collect 任务缺少 run_id")
    result = await collect_trends(session, run_id)
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
            with SessionLocal() as session:
                task = tq.claim_next(session)
                if task is None:
                    break

                payload = json.loads(task.payload or "{}")
                handler = _HANDLERS.get(task.task_type)

                if handler is None:
                    tq.mark_failed(session, task.id, f"未知任务类型: {task.task_type}", MAX_ATTEMPTS)
                    continue

                # 每次任务都重新读 settings，支持热更新 AI provider 配置
                settings = session.get(Settings, 1)
                if task.task_type in {"embed", "link_discover"} and (
                    settings is None or not settings.embed_model or not settings.embed_dim
                ):
                    # Settings 尚未配置，回退到 pending，不累计重试次数
                    task.status = "pending"
                    task.attempts -= 1
                    session.commit()
                    logger.debug("Settings 未配置，任务 %s 保持 pending", task.id)
                    break

                try:
                    await handler(session, payload, settings)
                    tq.mark_done(session, task.id)
                except Exception as exc:
                    logger.exception("任务 %s 执行失败: %s", task.id, exc)
                    if task.task_type == "embed" and payload.get("atom_id"):
                        mark_atom_embedding_error(session, payload["atom_id"], str(exc))
                    tq.mark_failed(session, task.id, str(exc), MAX_ATTEMPTS)


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
