"""应用配置：环境变量层（与数据库 settings 表区分）。"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPARKLING_",
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
    )

    db_path: str
    host: str
    port: int
    dev_origin: str

    @field_validator("db_path")
    @classmethod
    def normalize_db_path(cls, value: str) -> str:
        """SPARKLING_DB_PATH 是文件路径，不是 SQLAlchemy URL。"""
        if value.startswith("sqlite:"):
            msg = "SPARKLING_DB_PATH must be a filesystem path, not a SQLAlchemy URL"
            raise ValueError(msg)
        path = Path(os.path.expanduser(value))
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return str(path.resolve())

    @property
    def sqlalchemy_url(self) -> str:
        return f"sqlite:///{self.db_path}"


config = AppConfig()
