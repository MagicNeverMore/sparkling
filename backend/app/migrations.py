"""运行 Alembic migration 的轻量封装。"""
from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

from .config import BACKEND_DIR
from .logger import get_logger

logger = get_logger(__name__)


class SchemaCompatibilityError(RuntimeError):
    """数据库 migration revision 与应用所需 schema 不一致。"""


_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "task_queue": {"dedupe_key"},
    "social_media_video": {"external_video_id", "published_at"},
    "social_media_video_metric": {"video_id", "data_date", "updated_at"},
    "content_topic": {"status", "task_id", "scheduled_at"},
    "content_topic_publication": {"topic_id", "platform"},
}


def _validate_required_schema(engine: Engine) -> None:
    """迁移后验证关键 column，防止 revision 已更新但实际 DDL 缺失。"""
    schema = inspect(engine)
    missing: list[str] = []
    for table_name, required_columns in _REQUIRED_COLUMNS.items():
        if not schema.has_table(table_name):
            missing.append(f"table:{table_name}")
            continue
        actual_columns = {column["name"] for column in schema.get_columns(table_name)}
        missing.extend(
            f"column:{table_name}.{column_name}"
            for column_name in sorted(required_columns - actual_columns)
        )
    if missing:
        raise SchemaCompatibilityError(
            "数据库 schema 与当前应用版本不兼容，缺少：" + ", ".join(missing)
        )


def run_migrations_for_engine(engine: Engine, *, render_as_batch: bool) -> None:
    """在指定 engine 上升级到 head。

    用于热切换时准备目标业务数据库，避免依赖当前全局 engine。
    """
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_cfg.attributes["render_as_batch"] = render_as_batch
    # 应用进程已经安装统一的 console/file handlers。嵌入式 Alembic 若再次执行
    # fileConfig，会移除这些 handlers，导致 migration 后所有业务日志消失。
    alembic_cfg.attributes["preserve_app_logging"] = True
    logger.info(
        "开始执行 Alembic migration backend=%s render_as_batch=%s",
        engine.dialect.name,
        render_as_batch,
    )
    try:
        with engine.connect() as connection:
            alembic_cfg.attributes["connection"] = connection
            command.upgrade(alembic_cfg, "head")
        _validate_required_schema(engine)
    except Exception:
        logger.exception("Alembic migration 或 schema 校验失败 backend=%s", engine.dialect.name)
        raise
    logger.info("Alembic migration 已升级到 head，schema 校验通过")
