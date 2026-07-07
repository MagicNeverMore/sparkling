"""本地任务队列：入队、领取、完成、失败标记。

不引入 Redis，通过 asyncio.Event 唤醒 worker，SQLite 写锁保证并发安全。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session, aliased

from ..logger import get_logger
from ..models import TaskQueue

logger = get_logger(__name__)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 30
MAX_RETRY_DELAY_SECONDS = 3600

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


def enqueue(
    session: Session,
    task_type: str,
    payload: dict,
    *,
    priority: int = 0,
    resource_key: str | None = None,
    available_at: datetime | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> TaskQueue:
    """插入 pending 任务并唤醒 worker。"""
    task = TaskQueue(
        task_type=task_type,
        payload=json.dumps(payload, ensure_ascii=False),
        status="pending",
        attempts=0,
        max_attempts=max(1, int(max_attempts or DEFAULT_MAX_ATTEMPTS)),
        priority=int(priority or 0),
        available_at=available_at or datetime.utcnow(),
        resource_key=resource_key or default_resource_key(task_type, payload),
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


def default_resource_key(task_type: str, payload: dict[str, Any] | None) -> str | None:
    """按任务类型推导资源锁 key。"""
    payload = payload or {}
    if task_type in {"embed", "link_discover"} and payload.get("atom_id"):
        return f"atom:{payload['atom_id']}"
    if task_type == "trend_collect":
        return "trend_collect"
    return None


def claim_next(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 180,
    lease_seconds_by_type: dict[str, int] | None = None,
    excluded_task_ids: set[str] | None = None,
    blocked_task_types: set[str] | None = None,
) -> TaskQueue | None:
    """原子领取一条可执行任务。

    领取前会跳过尚未到 available_at、类型已满、资源正在被有效 running 任务占用的任务。
    """
    now = datetime.utcnow()
    active_resource_keys = {
        row[0]
        for row in (
            session.query(TaskQueue.resource_key)
            .filter(TaskQueue.status == "running")
            .filter(TaskQueue.resource_key.is_not(None))
            .filter(or_(TaskQueue.lease_until.is_(None), TaskQueue.lease_until > now))
            .all()
        )
    }

    query = (
        session.query(TaskQueue)
        .filter(TaskQueue.status == "pending")
        .filter(or_(TaskQueue.available_at.is_(None), TaskQueue.available_at <= now))
    )
    if excluded_task_ids:
        query = query.filter(TaskQueue.id.notin_(excluded_task_ids))
    if blocked_task_types:
        query = query.filter(TaskQueue.task_type.notin_(blocked_task_types))

    candidates = query.order_by(TaskQueue.priority.desc(), TaskQueue.created_at.asc()).limit(50).all()
    for candidate in candidates:
        if candidate.resource_key and candidate.resource_key in active_resource_keys:
            logger.debug("任务 %s 资源锁冲突，跳过 resource=%s", candidate.id, candidate.resource_key)
            continue

        task_lease_seconds = (lease_seconds_by_type or {}).get(candidate.task_type, lease_seconds)
        lease_until = now + timedelta(seconds=max(1, int(task_lease_seconds)))
        updated = (
            session.query(TaskQueue)
            .filter(TaskQueue.id == candidate.id)
            .filter(TaskQueue.status == "pending")
            .filter(or_(TaskQueue.available_at.is_(None), TaskQueue.available_at <= now))
        )
        if candidate.resource_key:
            active_task = aliased(TaskQueue)
            updated = updated.filter(
                ~exists()
                .where(active_task.status == "running")
                .where(active_task.resource_key == candidate.resource_key)
                .where(or_(active_task.lease_until.is_(None), active_task.lease_until > now))
            )
        updated_count = updated.update(
            {
                "status": "running",
                "attempts": TaskQueue.attempts + 1,
                "locked_by": worker_id,
                "locked_at": now,
                "lease_until": lease_until,
                "last_error": None,
                "updated_at": now,
            },
            synchronize_session=False,
        )
        if updated_count != 1:
            session.rollback()
            continue
        session.commit()
        task = session.get(TaskQueue, candidate.id)
        if task is not None:
            logger.debug("已领取任务 id=%s type=%s lease_until=%s", task.id, task.task_type, task.lease_until)
        return task

    return None


def mark_done(session: Session, task_id: str) -> None:
    """将任务标记为完成。"""
    task = session.get(TaskQueue, task_id)
    if task:
        task.status = "done"
        task.locked_by = None
        task.locked_at = None
        task.lease_until = None
        task.updated_at = datetime.utcnow()
        session.commit()


def mark_failed(session: Session, task_id: str, error: str, max_attempts: int | None = None) -> str | None:
    """标记任务失败；未达最大重试次数则重置为 pending 允许重试。"""
    task = session.get(TaskQueue, task_id)
    if not task:
        return None
    now = datetime.utcnow()
    allowed_attempts = max(1, int(max_attempts or task.max_attempts or DEFAULT_MAX_ATTEMPTS))
    task.last_error = error[:2000]
    task.locked_by = None
    task.locked_at = None
    task.lease_until = None
    task.updated_at = now
    if task.attempts >= allowed_attempts:
        task.status = "failed"
        logger.warning("任务 %s 超过最大重试次数，标记为 failed: %s", task_id, error)
    else:
        task.status = "pending"
        task.available_at = now + timedelta(seconds=_retry_delay_seconds(task.attempts))
        logger.info(
            "任务 %s 失败，将重试（attempts=%d available_at=%s）: %s",
            task_id,
            task.attempts,
            task.available_at,
            error,
        )
    session.commit()
    return task.status


def release_running(session: Session, task_id: str, reason: str) -> None:
    """worker 停止或取消时释放 running 任务，避免长期卡住。"""
    task = session.get(TaskQueue, task_id)
    if not task or task.status != "running":
        return
    task.status = "pending"
    task.attempts = max(0, task.attempts - 1)
    task.last_error = reason[:2000]
    task.available_at = datetime.utcnow()
    task.locked_by = None
    task.locked_at = None
    task.lease_until = None
    task.updated_at = datetime.utcnow()
    session.commit()


def reclaim_expired_leases(session: Session, now: datetime | None = None) -> int:
    """回收超出 lease 的 running 任务。"""
    now = now or datetime.utcnow()
    tasks = (
        session.query(TaskQueue)
        .filter(TaskQueue.status == "running")
        .filter(TaskQueue.lease_until.is_not(None))
        .filter(TaskQueue.lease_until <= now)
        .all()
    )
    for task in tasks:
        task.locked_by = None
        task.locked_at = None
        task.lease_until = None
        task.updated_at = now
        if task.attempts >= max(1, task.max_attempts or DEFAULT_MAX_ATTEMPTS):
            task.status = "failed"
            task.last_error = (task.last_error or "任务租约超时")[:2000]
            logger.warning("任务 %s 租约超时且超过最大次数，标记 failed", task.id)
        else:
            task.status = "pending"
            task.available_at = now
            task.last_error = (task.last_error or "任务租约超时，已回收")[:2000]
            logger.info("任务 %s 租约超时，已回收为 pending", task.id)
    session.commit()
    return len(tasks)


def retry_failed(session: Session, task_type: str | None = None) -> int:
    """将 failed 任务重新置为 pending，返回重试数量。"""
    query = session.query(TaskQueue).filter(TaskQueue.status == "failed")
    if task_type is not None:
        query = query.filter(TaskQueue.task_type == task_type)
    tasks = query.all()
    now = datetime.utcnow()
    for task in tasks:
        task.status = "pending"
        task.attempts = 0
        task.last_error = None
        task.available_at = now
        task.locked_by = None
        task.locked_at = None
        task.lease_until = None
        task.updated_at = now
    session.commit()
    if tasks:
        try:
            get_wakeup_event().set()
        except RuntimeError:
            pass
    return len(tasks)


def _retry_delay_seconds(attempts: int) -> int:
    exponent = max(0, int(attempts or 1) - 1)
    return min(MAX_RETRY_DELAY_SECONDS, DEFAULT_RETRY_DELAY_SECONDS * (2 ** exponent))
