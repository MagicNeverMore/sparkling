"""应用配置：环境变量层（与数据库 settings 表区分）。

业务数据库选择保存在固定 control SQLite 中，环境变量只负责提供首次启动的
默认 SQLite 文件路径，以及服务监听配置。PostgreSQL URL 不再通过 .env 注入。
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator, model_validator
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

    db_path: str = str(BACKEND_DIR / "sparkling.db")
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
        """首次启动必须有默认 SQLite 文件路径。"""
        if not self.db_path:
            raise ValueError("必须配置 SPARKLING_DB_PATH（SQLite 文件路径）")
        return self


config = AppConfig()
logger.info(
    "应用配置已加载 host=%s port=%s default_db_path=%s dev_origin=%s",
    config.host,
    config.port,
    config.db_path,
    config.dev_origin,
)
