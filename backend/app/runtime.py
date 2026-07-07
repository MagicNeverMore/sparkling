"""进程级运行时状态。"""
from __future__ import annotations

import asyncio

from .logger import get_logger
from .workers.runner import start_worker, stop_worker

_worker_task: asyncio.Task | None = None
logger = get_logger(__name__)


async def start_background_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        logger.debug("后台 worker 已在运行，跳过启动")
        return
    logger.info("准备启动后台 worker")
    _worker_task = await start_worker()


async def stop_background_worker() -> None:
    global _worker_task
    logger.info("准备停止后台 worker")
    await stop_worker(_worker_task)
    _worker_task = None


async def restart_background_worker() -> None:
    logger.info("准备重启后台 worker")
    await stop_background_worker()
    await start_background_worker()
