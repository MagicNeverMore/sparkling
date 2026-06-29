"""运行 Alembic migration 的轻量封装。"""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from .config import BACKEND_DIR


def run_migrations_for_engine(engine: Engine, *, render_as_batch: bool) -> None:
    """在指定 engine 上升级到 head。

    用于热切换时准备目标业务数据库，避免依赖当前全局 engine。
    """
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_cfg.attributes["render_as_batch"] = render_as_batch
    with engine.connect() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
