"""统一日志管理：控制台 + 有容量上限的文件日志。

使用方式：
    from app.logger import get_logger
    logger = get_logger(__name__)
    logger.info("something happened", extra={"atom_id": "..."})

日志文件保存在 backend/logs/，按大小轮转，并限制整个日志目录的占用空间。
"""
from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志根目录：本地默认 backend/logs；Docker 使用 /data/logs 随 volume 持久化。
LOG_DIR = Path(
    os.path.expanduser(
        os.getenv("SPARKLING_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
    )
).resolve()

# 全局日志级别与容量限制可由环境变量覆盖。
LOG_LEVEL_NAME = os.getenv("SPARKLING_LOG_LEVEL", "DEBUG").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.DEBUG)
LOG_MAX_TOTAL_BYTES = max(4, int(os.getenv("SPARKLING_LOG_MAX_TOTAL_MB", "200"))) * 1024 * 1024
_requested_max_file_bytes = (
    max(1, int(os.getenv("SPARKLING_LOG_MAX_FILE_MB", "10"))) * 1024 * 1024
)
# 两个 active 文件各至少预留一个同等大小的 backup，保证配置总量可兑现。
LOG_MAX_FILE_BYTES = min(_requested_max_file_bytes, LOG_MAX_TOTAL_BYTES // 4)
_max_backups_per_family = max(1, LOG_MAX_TOTAL_BYTES // (2 * LOG_MAX_FILE_BYTES) - 1)
LOG_BACKUP_COUNT = min(
    max(1, int(os.getenv("SPARKLING_LOG_BACKUP_COUNT", "9"))),
    _max_backups_per_family,
)
LOG_FORMAT = "%(asctime)s | pid=%(process)d | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MANAGED_LOG_FILE_NAME = re.compile(
    r"^(?:sparkling|error)\.log(?:\.(?:\d+|\d{4}-\d{2}-\d{2}(?:\.\d+)?))?$"
)

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
        message = redact_log_text(record.getMessage())
        record.msg = (
            message
            if len(message) <= 100_000
            else f"{message[:100_000]}... [TRUNCATED BY LOG SIZE LIMIT]"
        )
        record.args = ()
        return True


def _managed_log_files(log_dir: Path) -> list[Path]:
    if not log_dir.exists():
        return []
    return [
        path
        for path in log_dir.iterdir()
        if path.is_file() and _MANAGED_LOG_FILE_NAME.fullmatch(path.name)
    ]


def managed_log_size(log_dir: Path = LOG_DIR) -> int:
    """返回 Sparkling 管理的日志文件总大小，不计算目录中的其他文件。"""
    total = 0
    for path in _managed_log_files(log_dir):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def prune_log_directory(
    log_dir: Path = LOG_DIR,
    *,
    max_total_bytes: int = LOG_MAX_TOTAL_BYTES,
) -> list[str]:
    """从最旧 backup 开始清理，active 日志和非 Sparkling 文件永不删除。"""
    files = _managed_log_files(log_dir)
    sizes: dict[Path, int] = {}
    for path in files:
        try:
            sizes[path] = path.stat().st_size
        except OSError:
            continue
    total = sum(sizes.values())
    candidates = [path for path in sizes if path.name not in {"sparkling.log", "error.log"}]
    candidates.sort(key=lambda path: (path.stat().st_mtime, path.name))

    removed: list[str] = []
    for path in candidates:
        if total <= max_total_bytes:
            break
        try:
            path.unlink()
        except OSError:
            continue
        total -= sizes[path]
        removed.append(path.name)
    return removed


class _SizeBoundRotatingFileHandler(RotatingFileHandler):
    """大小轮转后同步执行目录级清理，兼容移除旧的按日期 backup。"""

    def __init__(self, *args: object, max_total_bytes: int, **kwargs: object) -> None:
        self._max_total_bytes = max_total_bytes
        super().__init__(*args, **kwargs)

    def doRollover(self) -> None:
        super().doRollover()
        # 为 sparkling.log 和 error.log 的后续增长各预留一个 maxBytes。
        cleanup_target = max(0, self._max_total_bytes - 2 * self.maxBytes)
        prune_log_directory(Path(self.baseFilename).parent, max_total_bytes=cleanup_target)


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

    # 先清理旧版本遗留的按日期日志，再创建有大小上限的 handler。
    log_dir = _ensure_log_dir()
    cleanup_target = max(0, LOG_MAX_TOTAL_BYTES - 2 * LOG_MAX_FILE_BYTES)
    removed_logs = prune_log_directory(log_dir, max_total_bytes=cleanup_target)

    # ── 文件 handler：按大小轮转 ──
    file_handler = _SizeBoundRotatingFileHandler(
        filename=log_dir / "sparkling.log",
        maxBytes=LOG_MAX_FILE_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        max_total_bytes=LOG_MAX_TOTAL_BYTES,
        encoding="utf-8",
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_SensitiveDataFilter())
    if Path(file_handler.baseFilename).stat().st_size > LOG_MAX_FILE_BYTES:
        file_handler.doRollover()
    root.addHandler(file_handler)

    # ── 错误日志单独文件 ──
    error_handler = _SizeBoundRotatingFileHandler(
        filename=log_dir / "error.log",
        maxBytes=LOG_MAX_FILE_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        max_total_bytes=LOG_MAX_TOTAL_BYTES,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(_SensitiveDataFilter())
    if Path(error_handler.baseFilename).stat().st_size > LOG_MAX_FILE_BYTES:
        error_handler.doRollover()
    root.addHandler(error_handler)

    # 强制轮转旧 active 文件后再次收紧目录，确保为后续写入保留容量。
    removed_logs.extend(prune_log_directory(log_dir, max_total_bytes=cleanup_target))

    # 降低第三方库的日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)

    root.info(
        "日志系统初始化完成 log_dir=%s level=%s max_file_mb=%s backups=%s "
        "max_total_mb=%s pruned_files=%s",
        LOG_DIR,
        LOG_LEVEL_NAME,
        LOG_MAX_FILE_BYTES // (1024 * 1024),
        LOG_BACKUP_COUNT,
        LOG_MAX_TOTAL_BYTES // (1024 * 1024),
        len(removed_logs),
    )


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。setup_logging() 需先调用一次。"""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
