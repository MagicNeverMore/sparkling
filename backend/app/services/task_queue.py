"""SQLite 任务队列：入队、领取、完成、失败标记。

不引入 Redis，通过 asyncio.Event 唤醒 worker，SQLite 写锁保证并发安全。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import TaskQueue

logger = logging.getLogger(__name__)

# 模块级唤醒事件，enqueue 后 set()，worker loop 监听
_wakeup: asyncio.Event | None = None


def get_wakeup_event() -> asyncio.Event:
    """获取（或延迟初始化）唤醒事件。

    在 asyncio event loop 中首次调用时才创建，避免 import 阶段无 loop 的问题。
    """
    global _wakeup
    if _wakeup is None:
        _wakeup = asyncio.Event()
    return _wakeup


def enqueue(session: Session, task_type: str, payload: dict) -> TaskQueue:
    """插入 pending 任务并唤醒 worker。"""
    task = TaskQueue(
        task_type=task_type,
        payload=json.dumps(payload, ensure_ascii=False),
        status="pending",
        attempts=0,
    )
    session.add(task)
    session.commit()
    # 通知 worker 有新任务可处理
    try:
        get_wakeup_event().set()
    except RuntimeError:
        # 在非 asyncio 上下文中调用时忽略（测试场景）
        pass
    logger.debug("已入队任务 type=%s payload=%s", task_type, payload)
    return task


def claim_next(session: Session) -> TaskQueue | None:
    """原子地领取一条 pending 任务，将状态改为 running。

    SQLite 单写锁保证同时只有一个 worker 能领取同一条任务。
    """
    task = (
        session.query(TaskQueue)
        .filter(TaskQueue.status == "pending")
        .order_by(TaskQueue.created_at.asc())
        .with_for_update()
        .first()
    )
    if task is None:
        return None
    task.status = "running"
    task.attempts += 1
    task.updated_at = datetime.utcnow()
    session.commit()
    return task


def mark_done(session: Session, task_id: str) -> None:
    """将任务标记为完成。"""
    task = session.get(TaskQueue, task_id)
    if task:
        task.status = "done"
        task.updated_at = datetime.utcnow()
        session.commit()


def mark_failed(session: Session, task_id: str, error: str, max_attempts: int = 3) -> None:
    """标记任务失败；未达最大重试次数则重置为 pending 允许重试。"""
    task = session.get(TaskQueue, task_id)
    if not task:
        return
    task.last_error = error[:2000]
    task.updated_at = datetime.utcnow()
    if task.attempts >= max_attempts:
        task.status = "failed"
        logger.warning("任务 %s 超过最大重试次数，标记为 failed: %s", task_id, error)
    else:
        task.status = "pending"
        logger.info("任务 %s 失败，将重试（attempts=%d）: %s", task_id, task.attempts, error)
    session.commit()
