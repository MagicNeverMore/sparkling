"""统一日志管理：控制台 + 按日期轮转的文件日志。

使用方式：
    from app.logger import get_logger
    logger = get_logger(__name__)
    logger.info("something happened", extra={"atom_id": "..."})

日志文件保存在 backend/logs/，按天轮转，保留最近 30 天。
"""
from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 日志根目录：backend/logs/（app/logger.py → 上两级 = backend/）
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# 全局日志级别与保留天数可由环境变量覆盖
LOG_LEVEL_NAME = os.getenv("SPARKLING_LOG_LEVEL", "DEBUG").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.DEBUG)
LOG_RETENTION_DAYS = max(1, int(os.getenv("SPARKLING_LOG_RETENTION_DAYS", "30")))
LOG_FORMAT = "%(asctime)s | pid=%(process)d | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(client_secret|refresh_token|access_token|oauth_state|"
    r"(?:^|[?&\s])(code|state))([=:]\s*|%3[dD])([^&\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")

_initialized = False


def redact_log_text(value: object) -> str:
    """对日志文本做兜底脱敏，避免 OAuth 凭据进入统一日志文件。"""
    text = str(value)
    text = _BEARER_TOKEN.sub(r"\1[REDACTED]", text)
    return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


class _SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_log_text(record.getMessage())
        record.args = ()
        return True


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def setup_logging() -> None:
    """初始化全局日志配置。幂等，多次调用只生效一次。"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # ── 控制台 handler ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(LOG_LEVEL)
    console.setFormatter(formatter)
    console.addFilter(_SensitiveDataFilter())
    root.addHandler(console)

    # ── 文件 handler：按天轮转，保留 30 天 ──
    log_dir = _ensure_log_dir()
    file_handler = TimedRotatingFileHandler(
        filename=log_dir / "sparkling.log",
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_SensitiveDataFilter())
    root.addHandler(file_handler)

    # ── 错误日志单独文件 ──
    error_handler = TimedRotatingFileHandler(
        filename=log_dir / "error.log",
        when="midnight",
        interval=1,
        backupCount=LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(_SensitiveDataFilter())
    root.addHandler(error_handler)

    # 降低第三方库的日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    root.info(
        "日志系统初始化完成 log_dir=%s level=%s retention_days=%s",
        LOG_DIR,
        LOG_LEVEL_NAME,
        LOG_RETENTION_DAYS,
    )


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。setup_logging() 需先调用一次。"""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
