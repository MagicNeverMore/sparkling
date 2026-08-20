"""受控读取 Sparkling 轮转日志，供 Settings 中的 Logs 页面使用。"""
from __future__ import annotations

import re
from datetime import UTC, datetime

from ...logger import LOG_DIR, redact_log_text

_LOG_FILE_NAME = re.compile(
    r"^(?:sparkling|error)\.log(?:\.(?:\d+|\d{4}-\d{2}-\d{2}(?:\.\d+)?))?$"
)
_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_MAX_LINE_CHARS = 20_000


def list_log_files() -> list[dict[str, object]]:
    if not LOG_DIR.exists():
        return []
    files = [path for path in LOG_DIR.iterdir() if path.is_file() and _LOG_FILE_NAME.fullmatch(path.name)]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [
        {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        }
        for path in files
    ]


def read_log_page(
    *,
    file_name: str | None = None,
    level: str | None = None,
    query: str | None = None,
    before: int | None = None,
    limit: int = 200,
) -> dict[str, object]:
    files = list_log_files()
    available = {str(item["name"]) for item in files}
    selected = file_name or (
        "sparkling.log" if "sparkling.log" in available else (str(files[0]["name"]) if files else None)
    )
    if selected is None:
        return {
            "file": None,
            "files": files,
            "total_matches": 0,
            "next_before": None,
            "items": [],
        }
    if selected not in available or not _LOG_FILE_NAME.fullmatch(selected):
        raise ValueError("日志文件不存在或不允许访问")

    normalized_level = level.upper() if level else None
    if normalized_level and normalized_level not in _LEVELS:
        raise ValueError("不支持的日志级别")
    normalized_query = (query or "").strip().casefold()
    page_limit = max(1, min(int(limit), 500))
    lines = (LOG_DIR / selected).read_text(encoding="utf-8", errors="replace").splitlines()

    matches: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if normalized_level and not re.search(rf"\|\s*{re.escape(normalized_level)}\s*\|", line):
            continue
        if normalized_query and normalized_query not in line.casefold():
            continue
        matches.append(
            {
                "line_number": line_number,
                "text": redact_log_text(line[:_MAX_LINE_CHARS]),
            }
        )

    cursor = before if before is not None else len(lines) + 1
    eligible = [item for item in matches if int(item["line_number"]) < cursor]
    page_items = eligible[-page_limit:]
    next_before = int(page_items[0]["line_number"]) if len(eligible) > len(page_items) else None
    return {
        "file": selected,
        "files": files,
        "total_matches": len(matches),
        "next_before": next_before,
        "items": page_items,
    }
