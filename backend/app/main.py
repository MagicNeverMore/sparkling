"""FastAPI 入口：挂载路由、WebSocket、静态前端，启动后台 worker。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from .config import config
from .db import DatabaseConnectionError, configure_current_database, get_database_backend, get_engine, uses_postgresql
from .logger import get_logger, setup_logging
from .migrations import run_migrations_for_engine
from .routers import atoms, auth, graph, links, logs, search, settings, social_media, tasks, trends, ws
from .runtime import start_background_worker, stop_background_worker
from .services import auth as auth_service

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    logger.info("━━━ Sparkling 启动 ━━━")
    try:
        run_migrations_for_engine(get_engine(), render_as_batch=not uses_postgresql())
        configure_current_database()
        logger.info("数据库连接成功 (backend=%s)", get_database_backend())
        await start_background_worker()
        logger.info("后台 worker 已启动")
    except Exception as exc:
        logger.exception(
            "数据库初始化或 migration 失败，HTTP 服务将继续启动但后台 worker 不会启动: %s",
            exc,
        )
    try:
        yield
    finally:
        logger.info("━━━ Sparkling 关闭 ━━━")
        await stop_background_worker()
        logger.info("后台 worker 已停止")


app = FastAPI(title="Sparkling", lifespan=lifespan)

AUTH_EXEMPT_API_PATHS = {
    "/api/auth/status",
    "/api/auth/register",
    "/api/auth/login",
    "/api/health",
    # OAuth state 已提供一次性请求校验；callback 不能依赖跨站返回时的 session cookie。
    "/api/social-media/youtube/oauth/callback",
}


def _database_error_message(exc: Exception) -> str:
    if isinstance(exc, DBAPIError) and exc.orig is not None:
        return f"数据库连接失败：{exc.orig}"
    return f"数据库连接失败：{exc}"


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception(
        "数据库请求执行失败 method=%s path=%s error=%s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=503,
        content={"message": _database_error_message(exc), "detail": str(exc)},
    )


@app.exception_handler(DatabaseConnectionError)
async def database_connection_exception_handler(
    request: Request,
    exc: DatabaseConnectionError,
) -> JSONResponse:
    logger.exception(
        "数据库连接异常 method=%s path=%s error=%s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=503,
        content={"message": str(exc), "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """确保被 FastAPI 转换为响应前，所有未处理异常均进入统一日志。"""
    logger.exception(
        "未处理的请求异常 method=%s path=%s error_type=%s error=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"message": "程序运行发生未处理错误，请检查 Logs", "detail": str(exc)},
    )


@app.middleware("http")
async def require_auth_for_api(request: Request, call_next):  # noqa: ANN001
    """保护业务 API；静态 SPA 资源保持可加载，由前端显示登录页。"""
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        token = request.cookies.get(auth_service.SESSION_COOKIE_NAME)
        user = auth_service.get_user_by_session(token)
        request.state.user = user
        if request.url.path not in AUTH_EXEMPT_API_PATHS and user is None:
            return JSONResponse(
                status_code=401,
                content={"message": "Unauthorized", "detail": "Unauthorized"},
            )
    return await call_next(request)

# 开发期允许前端 dev server 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.dev_origin] if config.dev_origin else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(logs.router, prefix="/api/settings/logs", tags=["settings"])
app.include_router(atoms.router, prefix="/api/atoms", tags=["atoms"])
app.include_router(links.router, prefix="/api/links", tags=["links"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(trends.router, prefix="/api/trends", tags=["trends"])
app.include_router(social_media.router, prefix="/api/social-media", tags=["social-media"])
app.include_router(ws.router, tags=["ws"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# —— 挂载静态前端（SPA fallback）——
_frontend_dir = Path(__file__).parent / "frontend"
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Content-Type-Options": "nosniff",
}
_IMMUTABLE_ASSET_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
}
_STATIC_FILES_WITHOUT_FALLBACK = {
    "manifest.webmanifest",
    "registerSW.js",
    "sw.js",
}


def _safe_frontend_file(full_path: str) -> Path | None:
    root = _frontend_dir.resolve()
    candidate = (root / (full_path or "index.html")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """返回静态文件；不匹配时回退到 index.html（支持 SPA 路由）。"""
    # API 路径不应走到这里（路由优先级高于此 catch-all），防御性排除
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    # 尝试匹配具体文件，否则回退到 index.html
    file_path = _safe_frontend_file(full_path)
    if file_path is not None:
        headers = _IMMUTABLE_ASSET_HEADERS if full_path.startswith("assets/") else _NO_CACHE_HEADERS
        return FileResponse(file_path, headers=headers)
    if full_path.startswith("assets/") or full_path in _STATIC_FILES_WITHOUT_FALLBACK:
        raise HTTPException(status_code=404, detail="Not found")
    index_path = _frontend_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path, headers=_NO_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Frontend not built")
