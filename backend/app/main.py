"""FastAPI 入口：挂载路由、WebSocket、静态前端，启动后台 worker。"""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from .config import config
from .db import engine
from .routers import atoms, graph, links, search, settings, tasks, ws
from .workers.runner import start_worker, stop_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task: asyncio.Task | None = None
    try:
        # 首次启动时启用 WAL 模式，提升读写并发性能
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
        task = await start_worker()
    except (SQLAlchemyError, sqlite3.Error):
        # 数据库不可达时仍保持 HTTP 服务启动，API handler 会返回可展示的 JSON message。
        task = None
    try:
        yield
    finally:
        await stop_worker(task)


app = FastAPI(title="Sparkling", lifespan=lifespan)


def _database_error_message(exc: Exception) -> str:
    if isinstance(exc, DBAPIError) and exc.orig is not None:
        return f"数据库连接失败：{exc.orig}"
    return f"数据库连接失败：{exc}"


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(_request, exc: SQLAlchemyError) -> JSONResponse:  # noqa: ANN001
    return JSONResponse(
        status_code=503,
        content={"message": _database_error_message(exc), "detail": str(exc)},
    )


@app.exception_handler(sqlite3.Error)
async def sqlite_exception_handler(_request, exc: sqlite3.Error) -> JSONResponse:  # noqa: ANN001
    return JSONResponse(
        status_code=503,
        content={"message": _database_error_message(exc), "detail": str(exc)},
    )

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


# —— 挂载静态前端（SPA fallback）——
_frontend_dir = Path(__file__).parent / "frontend"


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """返回静态文件；不匹配时回退到 index.html（支持 SPA 路由）。"""
    # API 路径不应走到这里（路由优先级高于此 catch-all），防御性排除
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    # 尝试匹配具体文件，否则回退到 index.html
    file_path = _frontend_dir / (full_path or "index.html")
    if file_path.is_file():
        return FileResponse(file_path)
    index_path = _frontend_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend not built")
