"""任务全天日期校验及可追踪的完成事件。"""
from datetime import date, datetime, timezone
import json
from uuid import uuid4

from ..logger import get_logger
from ..time_utils import get_timezone, utc_isoformat

logger = get_logger(__name__)


def validate_task_dates(start: str | None, due: str | None, actual: str | None,
                        completed: bool, timezone_name: str) -> None:
    today = datetime.now(get_timezone(timezone_name)).date()
    for label, value in (("开始日期", start), ("截止日期", due), ("实际完成日期", actual)):
        if value is not None:
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{label}必须是有效的 YYYY-MM-DD 日期") from exc
    if start and due and due < start:
        raise ValueError("截止日期不得早于开始日期")
    if actual and not completed:
        raise ValueError("未完成任务不能填写实际完成日期")
    if completed and not actual:
        raise ValueError("已完成任务必须填写实际完成日期")
    if actual and actual > today.isoformat():
        raise ValueError("实际完成日期不能晚于今天")
    if start and actual and actual < start:
        raise ValueError("实际完成日期不得早于开始日期")


def log_completion_change(task_id: str, old_completed: bool, completed: bool,
                          old_date: str | None, actual: str | None) -> None:
    if old_completed == completed and old_date == actual:
        return
    event = "task_completion_date_changed"
    if old_completed != completed:
        event = "task_completed" if completed else "task_reopened"
    logger.info(json.dumps({
        "time": utc_isoformat(datetime.now(timezone.utc)), "level": "INFO",
        "agent": "sparkling", "event": event, "msg": "任务完成信息已更新",
        "trace": str(uuid4()), "data": {"task_id": task_id,
            "previous_completed": old_completed, "completed": completed,
            "previous_date": old_date, "actual_completion_date": actual},
    }, ensure_ascii=False))
