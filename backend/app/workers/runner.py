"""后台 worker 入口 —— Task #5/#6 实现真实任务循环。

当前仅提供 start/stop 占位，让 lifespan 可以挂上。
"""
from __future__ import annotations

import asyncio
from typing import Optional


async def _worker_loop() -> None:
    # 真实循环在 Task #5 接入 task_queue 后实现
    while True:
        await asyncio.sleep(3600)


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
