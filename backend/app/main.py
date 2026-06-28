"""FastAPI 入口：挂载路由、WebSocket、静态前端，启动后台 worker。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .routers import atoms, graph, links, search, settings, tasks, ws
from .workers.runner import start_worker, stop_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动后台异步 worker（同进程）
    task = await start_worker()
    try:
        yield
    finally:
        await stop_worker(task)


app = FastAPI(title="Sparkling", lifespan=lifespan)

# 开发期允许前端 dev server 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.dev_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(atoms.router, prefix="/api/atoms", tags=["atoms"])
app.include_router(links.router, prefix="/api/links", tags=["links"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(ws.router, tags=["ws"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
