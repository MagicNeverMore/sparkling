"""SQLAlchemy engine 与 sqlite-vec 扩展加载。

提供两种访问方式：
- get_session()：FastAPI 依赖注入用的 Session（标准 ORM 操作）
- get_raw_conn()：拿到底层 sqlite3.Connection，用于 sqlite-vec 虚表的原生 SQL
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import config


class Base(DeclarativeBase):
    pass


# SQLite 在多线程下需要 check_same_thread=False；FastAPI 使用同步 ORM 时由 session 隔离
engine = create_engine(
    config.sqlalchemy_url,
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _load_extensions(dbapi_conn, _record):  # noqa: ANN001
    """每次新建底层连接时加载 sqlite-vec 扩展。"""
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)
    # 启用外键约束
    dbapi_conn.execute("PRAGMA foreign_keys = ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每次请求一个 Session。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_raw_conn() -> Iterator[sqlite3.Connection]:
    """获取原生 sqlite3 连接（用于 sqlite-vec 虚表 SQL）。"""
    conn = sqlite3.connect(config.db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
