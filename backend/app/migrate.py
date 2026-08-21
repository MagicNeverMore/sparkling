"""Docker/运维使用的 migration 入口，确保错误写入统一日志。"""
from __future__ import annotations

from .db import get_engine, uses_postgresql
from .logger import get_logger, setup_logging
from .migrations import run_migrations_for_engine

logger = get_logger(__name__)


def main() -> None:
    setup_logging()
    logger.info("开始执行启动前数据库 migration")
    try:
        engine = get_engine()
    except Exception:
        logger.exception("启动前无法初始化数据库 engine，Sparkling 将不会启动")
        raise
    try:
        run_migrations_for_engine(engine, render_as_batch=not uses_postgresql())
    except Exception:
        # migrations 层已经记录具体 traceback；这里只记录 entrypoint 终止语义。
        logger.error("启动前数据库 migration 失败，Sparkling 将不会启动")
        raise
    logger.info("启动前数据库 migration 完成")


if __name__ == "__main__":
    main()
