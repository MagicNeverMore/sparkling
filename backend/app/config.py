"""应用配置：环境变量层（与数据库 settings 表区分）。

支持两种数据库后端：
- SQLite（默认）：通过 SPARKLING_DB_PATH 指定文件路径
- PostgreSQL：通过 SPARKLING_POSTGRESQL_URL 指定连接串，优先级高于 SQLite
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logger import get_logger


BACKEND_DIR = Path(__file__).resolve().parents[1]
logger = get_logger(__name__)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPARKLING_",
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    db_backend: Literal["sqlite", "postgresql"] | None = Field(default=None)
    db_path: str = ""
    postgresql_url: str | None = None
    host: str = "127.0.0.1"
    port: int = 8000
    dev_origin: str = "http://localhost:5173"

    @field_validator("db_path")
    @classmethod
    def normalize_db_path(cls, value: str) -> str:
        """SPARKLING_DB_PATH 是文件路径，不是 SQLAlchemy URL。"""
        if not value:
            return value
        if value.startswith("sqlite:"):
            msg = "SPARKLING_DB_PATH must be a filesystem path, not a SQLAlchemy URL"
            raise ValueError(msg)
        path = Path(os.path.expanduser(value))
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return str(path.resolve())

    @model_validator(mode="after")
    def validate_db_config(self):
        """至少需要 SQLite 路径或 PostgreSQL URL 之一，并校验显式后端。"""
        if self.db_backend == "postgresql" and not self.postgresql_url:
            raise ValueError("使用 PostgreSQL 时必须配置 SPARKLING_POSTGRESQL_URL")
        if self.effective_db_backend == "sqlite" and not self.db_path:
            raise ValueError(
                "使用 SQLite 时必须配置 SPARKLING_DB_PATH（SQLite 文件路径）"
            )
        return self

    @property
    def effective_db_backend(self) -> Literal["sqlite", "postgresql"]:
        """实际使用的数据库后端；兼容旧配置中只设置 PostgreSQL URL 的情况。"""
        if self.db_backend:
            return self.db_backend
        if self.postgresql_url:
            return "postgresql"
        return "sqlite"

    @property
    def uses_postgresql(self) -> bool:
        """是否使用 PostgreSQL 后端。"""
        return self.effective_db_backend == "postgresql"

    @property
    def sqlalchemy_url(self) -> str:
        if self.uses_postgresql and self.postgresql_url:
            return self.postgresql_url
        if self.effective_db_backend == "sqlite" and self.db_path:
            return f"sqlite:///{self.db_path}"
        # 不应到达（model_validator 已拦截），防御性返回
        raise RuntimeError("未配置数据库连接")


config = AppConfig()
logger.info(
    "应用配置已加载 host=%s port=%s db_backend=%s dev_origin=%s",
    config.host,
    config.port,
    config.effective_db_backend,
    config.dev_origin,
)
