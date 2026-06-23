"""应用配置：环境变量层（与数据库 settings 表区分）。"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_db_path() -> str:
    # 默认本地 SQLite 路径，可被环境变量覆盖
    path = Path(os.path.expanduser("~/.sparkling/sparkling.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARKLING_", env_file=".env", extra="ignore")

    # SQLite 文件路径
    db_path: str = _default_db_path()
    # 监听地址（自托管单用户默认 127.0.0.1）
    host: str = "127.0.0.1"
    port: int = 8000
    # CORS 允许的前端 dev 源
    dev_origin: str = "http://localhost:5173"


config = AppConfig()
