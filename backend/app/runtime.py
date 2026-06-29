"""进程级运行时状态。"""
from __future__ import annotations

import asyncio

from .workers.runner import start_worker, stop_worker

_worker_task: asyncio.Task | None = None


async def start_background_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = await start_worker()


async def stop_background_worker() -> None:
    global _worker_task
    await stop_worker(_worker_task)
    _worker_task = None


async def restart_background_worker() -> None:
    await stop_background_worker()
    await start_background_worker()
