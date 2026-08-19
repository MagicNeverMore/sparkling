"""运行时数据库配置。

数据库选择不能存放在业务库里，否则业务库不可达时 Settings 页面也会失效。
这里使用一个独立的 control SQLite，只保存当前应连接到哪个业务数据库。
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from ...config import BACKEND_DIR, config
from ...logger import get_logger

CONTROL_DB_PATH = Path(
    os.path.expanduser(os.getenv("SPARKLING_CONTROL_DB_PATH", str(BACKEND_DIR / "control.db")))
)
if not CONTROL_DB_PATH.is_absolute():
    CONTROL_DB_PATH = BACKEND_DIR / CONTROL_DB_PATH
CONTROL_DB_PATH = CONTROL_DB_PATH.resolve()
logger = get_logger(__name__)


DatabaseBackend = Literal["sqlite", "postgresql"]


@dataclass(frozen=True)
class DatabaseRuntimeConfig:
    db_backend: DatabaseBackend
    db_path: str | None
    postgresql_url: str | None

    @property
    def uses_postgresql(self) -> bool:
        return self.db_backend == "postgresql"

    @property
    def sqlalchemy_url(self) -> str:
        if self.db_backend == "postgresql" and self.postgresql_url:
            return self.postgresql_url
        if self.db_backend == "sqlite" and self.db_path:
            return f"sqlite:///{self.db_path}"
        raise RuntimeError("未配置数据库连接")


def get_database_config() -> dict[str, str | bool | None]:
    """返回当前 runtime 数据库配置。"""
    runtime_config = load_database_config()
    return {
        "db_backend": runtime_config.db_backend,
        "db_path": runtime_config.db_path,
        "postgresql_url": runtime_config.postgresql_url,
        "restart_required": False,
    }


def load_database_config() -> DatabaseRuntimeConfig:
    """从 control SQLite 读取数据库配置；首次启动时写入默认 SQLite 配置。"""
    _ensure_control_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT db_backend, db_path, postgresql_url FROM database_config WHERE id = 1"
        ).fetchone()
    if row is None:
        seeded = _default_sqlite_config()
        save_database_config(seeded)
        logger.info("control DB 未找到数据库配置，已写入默认 SQLite 配置 path=%s", seeded.db_path)
        return seeded
    runtime_config = DatabaseRuntimeConfig(
        db_backend=row["db_backend"],
        db_path=row["db_path"],
        postgresql_url=row["postgresql_url"],
    )
    logger.debug("已从 control DB 读取数据库配置 backend=%s", runtime_config.db_backend)
    return runtime_config


def save_database_config(runtime_config: DatabaseRuntimeConfig) -> None:
    """保存当前数据库配置，不写 .env。"""
    _ensure_control_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO database_config (id, db_backend, db_path, postgresql_url, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              db_backend = excluded.db_backend,
              db_path = excluded.db_path,
              postgresql_url = excluded.postgresql_url,
              updated_at = excluded.updated_at
            """,
            (
                runtime_config.db_backend,
                runtime_config.db_path,
                runtime_config.postgresql_url,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    logger.info("数据库配置已保存到 control DB backend=%s", runtime_config.db_backend)


def build_database_config(
    db_backend: str,
    db_path: str | None,
    postgresql_url: str | None,
) -> DatabaseRuntimeConfig:
    """标准化用户输入。校验业务语义由 router/db manager 负责。"""
    if db_backend not in {"sqlite", "postgresql"}:
        logger.warning("数据库配置标准化失败：不支持的 backend=%s", db_backend)
        raise ValueError("db_backend must be sqlite or postgresql")

    normalized_path = None
    if db_path:
        path = Path(os.path.expanduser(db_path.strip()))
        if not path.is_absolute():
            path = BACKEND_DIR / path
        normalized_path = str(path.resolve())

    normalized_url = postgresql_url.strip() if postgresql_url else None

    runtime_config = DatabaseRuntimeConfig(
        db_backend=db_backend,
        db_path=normalized_path,
        postgresql_url=normalized_url,
    )
    logger.debug("数据库配置已标准化 backend=%s has_url=%s", db_backend, normalized_url is not None)
    return runtime_config


def _default_sqlite_config() -> DatabaseRuntimeConfig:
    """首次启动默认使用 SQLite；PostgreSQL 只通过 Settings 写入 control DB。"""
    return DatabaseRuntimeConfig(
        db_backend="sqlite",
        db_path=config.db_path or None,
        postgresql_url=None,
    )


def _connect() -> sqlite3.Connection:
    CONTROL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CONTROL_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def connect_control_db() -> sqlite3.Connection:
    """连接固定本地 control SQLite。

    control DB 不随业务数据库热切换，适合保存登录用户与数据库连接配置。
    """
    _ensure_control_db()
    logger.debug("连接 control DB path=%s", CONTROL_DB_PATH)
    return _connect()


def _ensure_control_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS database_config (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              db_backend TEXT NOT NULL CHECK (db_backend IN ('sqlite', 'postgresql')),
              db_path TEXT,
              postgresql_url TEXT,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_user (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              email TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_session (
              token_hash TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES auth_user(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS social_media_config (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              schedule_enabled INTEGER NOT NULL DEFAULT 1,
              update_frequency TEXT NOT NULL DEFAULT 'hourly',
              schedule_time TEXT NOT NULL DEFAULT '09:00',
              timezone TEXT NOT NULL DEFAULT 'UTC',
              youtube_client_id TEXT,
              youtube_client_secret TEXT,
              youtube_refresh_token TEXT,
              youtube_channel_id TEXT,
              youtube_channel_title TEXT,
              youtube_basic_job_id TEXT,
              youtube_reach_job_id TEXT,
              oauth_state TEXT,
              oauth_redirect_uri TEXT,
              last_run_at TEXT,
              next_run_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        now = datetime.utcnow().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT OR IGNORE INTO social_media_config (
              id, schedule_enabled, update_frequency, schedule_time, timezone, created_at, updated_at
            ) VALUES (1, 1, 'hourly', '09:00', 'UTC', ?, ?)
            """,
            (now, now),
        )
        # 旧版的 daily/weekly 表示抓取计划；现在统一升级为每小时查询，
        # 指标数据本身仍由 YouTube report 的 metric_date 保持日级。
        conn.execute(
            """
            UPDATE social_media_config
            SET update_frequency = 'hourly', next_run_at = NULL, updated_at = ?
            WHERE update_frequency IN ('daily', 'weekly')
            """,
            (now,),
        )
        conn.commit()
    logger.debug("control DB schema 已确认 path=%s", CONTROL_DB_PATH)
