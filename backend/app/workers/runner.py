"""后台 worker：轮询 task_queue，处理 embed 和 link_discover 任务。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from ..db import SessionLocal
from ..models import Settings
from ..services import task_queue as tq
from ..services.embedding import embed_atom
from ..services.linker import discover_links
from ..services.ws_manager import manager

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# 无新任务时的兜底轮询间隔（秒），防止 wakeup event 丢失
POLL_INTERVAL = 30.0


async def _handle_embed(session, payload: dict, settings: Settings) -> None:
    """处理 embed 任务：生成向量 → 写 vec_atoms → 入队 link_discover。"""
    atom_id = payload.get("atom_id")
    if not atom_id:
        raise ValueError("embed 任务缺少 atom_id")
    await embed_atom(session, atom_id, settings)
    # embed 完成后立即触发关联发现
    tq.enqueue(session, "link_discover", {"atom_id": atom_id})
    logger.info("embed 完成，已入队 link_discover，atom_id=%s", atom_id)


async def _handle_link_discover(session, payload: dict, settings: Settings) -> None:
    """处理 link_discover 任务：KNN 发现语义关联 → 写 DB → 广播给前端。"""
    atom_id = payload.get("atom_id")
    if not atom_id:
        raise ValueError("link_discover 任务缺少 atom_id")
    links = await discover_links(session, atom_id, settings, manager)
    logger.info("link_discover 完成，atom_id=%s，发现关联 %d 条", atom_id, len(links))


_HANDLERS = {
    "embed": _handle_embed,
    "link_discover": _handle_link_discover,
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

    while True:
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
                if settings is None or not settings.embed_model or not settings.embed_dim:
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
