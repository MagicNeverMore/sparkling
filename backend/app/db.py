"""运行时数据库连接管理。

业务数据库支持 SQLite / PostgreSQL 热切换。数据库选择本身存放在 control
SQLite 中，不依赖当前业务库连通性。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal
from urllib.parse import quote

import sqlite_vec
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .logger import get_logger
from .services.settings.runtime_config import (
    DatabaseRuntimeConfig,
    load_database_config,
    save_database_config,
)

DatabaseBackend = Literal["sqlite", "postgresql"]
logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


class DatabaseConnectionError(RuntimeError):
    """目标数据库不可用。"""


class DatabaseManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._config = load_database_config()
        self._engine: Engine | None = None
        self._sessionmaker: sessionmaker | None = None
        self._startup_error: DatabaseConnectionError | None = None
        try:
            logger.info("初始化数据库连接 backend=%s", self._config.db_backend)
            self._engine = self._create_engine(self._config)
            self._sessionmaker = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                future=True,
            )
            logger.info("数据库连接初始化完成 backend=%s", self._config.db_backend)
        except DatabaseConnectionError as exc:
            self._startup_error = exc
            logger.warning("数据库连接初始化失败 backend=%s error=%s", self._config.db_backend, exc)

    @property
    def backend(self) -> DatabaseBackend:
        with self._lock:
            return self._config.db_backend

    @property
    def uses_postgresql(self) -> bool:
        return self.backend == "postgresql"

    @property
    def sqlalchemy_url(self) -> str:
        with self._lock:
            return self._config.sqlalchemy_url

    def current_config(self) -> DatabaseRuntimeConfig:
        with self._lock:
            return self._config

    def get_engine(self) -> Engine:
        with self._lock:
            return self._require_engine()

    def create_session(self, **kwargs) -> Session:  # noqa: ANN003
        with self._lock:
            factory = self._require_sessionmaker()
        return factory(**kwargs)

    @contextmanager
    def raw_connection(self):
        with self._lock:
            cfg = self._config
            engine = self._require_engine()

        if cfg.db_backend == "sqlite":
            conn = self._connect_sqlite(cfg)
            self._setup_sqlite_connection(conn)
            try:
                yield conn
            finally:
                conn.close()
            return

        conn = engine.raw_connection()
        try:
            yield conn
        finally:
            conn.close()

    def configure_current_database(self) -> None:
        """启动或切换后执行轻量数据库级配置。"""
        with self._lock:
            cfg = self._config
            engine = self._require_engine()

        if cfg.db_backend != "sqlite":
            logger.debug("当前数据库 backend=%s，无需 SQLite PRAGMA 配置", cfg.db_backend)
            return
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
        logger.info("SQLite 数据库 PRAGMA 已配置")

    def switch(self, next_config: DatabaseRuntimeConfig) -> DatabaseRuntimeConfig:
        """验证并切换业务数据库。

        不做数据迁移；目标库会升级到当前 schema，然后成为新的 active database。
        """
        logger.info("开始切换业务数据库 backend=%s", next_config.db_backend)
        next_engine = self._create_engine(next_config)
        try:
            self._verify_engine(next_engine, next_config)
            self._run_migrations(next_engine, next_config)
        except Exception:
            next_engine.dispose()
            logger.exception("业务数据库切换验证失败 backend=%s", next_config.db_backend)
            raise

        next_sessionmaker = sessionmaker(
            bind=next_engine,
            autoflush=False,
            autocommit=False,
            future=True,
        )

        with self._lock:
            old_engine = self._engine
            self._config = next_config
            self._engine = next_engine
            self._sessionmaker = next_sessionmaker
            self._startup_error = None

        save_database_config(next_config)
        if old_engine is not None:
            old_engine.dispose()
        self.configure_current_database()
        logger.info("业务数据库切换完成 backend=%s", next_config.db_backend)
        return next_config

    def validate_target(self, target: DatabaseRuntimeConfig) -> None:
        """只验证目标数据库，不修改当前连接。"""
        logger.info("开始验证目标数据库 backend=%s", target.db_backend)
        engine = self._create_engine(target)
        try:
            self._verify_engine(engine, target)
        finally:
            engine.dispose()
        logger.info("目标数据库验证完成 backend=%s", target.db_backend)

    def _create_engine(self, cfg: DatabaseRuntimeConfig) -> Engine:
        if cfg.db_backend == "sqlite":
            path = self._sqlite_path(cfg)
            if not path.is_file():
                raise DatabaseConnectionError(f"SQLite 数据库文件不存在：{path}")
            logger.debug("创建 SQLite engine path=%s", path)
            engine = create_engine(
                "sqlite://",
                creator=lambda: self._connect_sqlite(cfg),
                future=True,
            )

            @event.listens_for(engine, "connect")
            def _load_extensions(dbapi_conn, _record):  # noqa: ANN001
                self._setup_sqlite_connection(dbapi_conn)

            return engine

        if not cfg.postgresql_url:
            raise DatabaseConnectionError("PostgreSQL URL 不能为空")
        try:
            url = make_url(cfg.postgresql_url)
        except ArgumentError as exc:
            raise DatabaseConnectionError(f"PostgreSQL URL 格式无效：{exc}") from exc
        if url.drivername not in {"postgresql", "postgresql+psycopg2"}:
            raise DatabaseConnectionError(
                "PostgreSQL URL 必须以 postgresql:// 或 postgresql+psycopg2:// 开头"
            )
        try:
            logger.debug("创建 PostgreSQL engine")
            engine = create_engine(
                cfg.postgresql_url,
                future=True,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
        except Exception as exc:
            raise DatabaseConnectionError(f"PostgreSQL URL 无法创建连接：{exc}") from exc

        @event.listens_for(engine, "connect")
        def _pg_setup(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.close()
            from pgvector.psycopg2 import register_vector

            register_vector(dbapi_conn)

        return engine

    def _require_engine(self) -> Engine:
        if self._engine is None:
            if self._startup_error is not None:
                raise self._startup_error
            raise DatabaseConnectionError("数据库连接尚未初始化")
        return self._engine

    def _require_sessionmaker(self) -> sessionmaker:
        if self._sessionmaker is None:
            if self._startup_error is not None:
                raise self._startup_error
            raise DatabaseConnectionError("数据库连接尚未初始化")
        return self._sessionmaker

    def _verify_engine(self, engine: Engine, cfg: DatabaseRuntimeConfig) -> None:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            raise DatabaseConnectionError(f"数据库连接失败：{exc}") from exc
        logger.debug("数据库 SELECT 1 验证通过 backend=%s", cfg.db_backend)

        if cfg.db_backend == "postgresql":
            try:
                with engine.begin() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception as exc:
                raise DatabaseConnectionError(f"PostgreSQL pgvector 扩展不可用：{exc}") from exc
            logger.debug("PostgreSQL pgvector 扩展验证通过")

    def _run_migrations(self, engine: Engine, cfg: DatabaseRuntimeConfig) -> None:
        from .migrations import run_migrations_for_engine

        run_migrations_for_engine(engine, render_as_batch=cfg.db_backend == "sqlite")

    def _sqlite_path(self, cfg: DatabaseRuntimeConfig) -> Path:
        if not cfg.db_path:
            raise DatabaseConnectionError("SQLite 数据库路径不能为空")
        return Path(cfg.db_path).expanduser().resolve()

    def _connect_sqlite(self, cfg: DatabaseRuntimeConfig) -> sqlite3.Connection:
        path = self._sqlite_path(cfg)
        db_uri = f"file:{quote(str(path))}?mode=rw"
        return sqlite3.connect(db_uri, uri=True, check_same_thread=False)

    @staticmethod
    def _setup_sqlite_connection(conn: sqlite3.Connection) -> None:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA foreign_keys = ON")


class _SessionLocalProxy:
    def __call__(self, **kwargs) -> Session:  # noqa: ANN003
        return database_manager.create_session(**kwargs)


class _EngineProxy:
    def connect(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return database_manager.get_engine().connect(*args, **kwargs)

    def begin(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return database_manager.get_engine().begin(*args, **kwargs)

    def raw_connection(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return database_manager.get_engine().raw_connection(*args, **kwargs)

    def dispose(self) -> None:
        database_manager.get_engine().dispose()


database_manager = DatabaseManager()
SessionLocal = _SessionLocalProxy()
engine = _EngineProxy()


def get_engine() -> Engine:
    return database_manager.get_engine()


def get_database_backend() -> DatabaseBackend:
    return database_manager.backend


def uses_postgresql() -> bool:
    return database_manager.uses_postgresql


def get_sqlalchemy_url() -> str:
    return database_manager.sqlalchemy_url


def get_current_database_config() -> DatabaseRuntimeConfig:
    return database_manager.current_config()


def switch_database(next_config: DatabaseRuntimeConfig) -> DatabaseRuntimeConfig:
    return database_manager.switch(next_config)


def validate_database_target(target: DatabaseRuntimeConfig) -> None:
    database_manager.validate_target(target)


def configure_current_database() -> None:
    database_manager.configure_current_database()


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_raw_conn():
    with database_manager.raw_connection() as conn:
        yield conn
