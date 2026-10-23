"""选题与任务的同步规则；调用方负责事务提交，日期按用户时区转换。"""
from datetime import date, datetime, time
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from ...logger import get_logger
from ...models import ContentTopic, UserTask
from ...time_utils import get_timezone, local_to_utc_naive, utc_naive_to_local, utc_isoformat
from ..task_dates import validate_task_dates

logger = get_logger(__name__)


def date_at_local_time(value: str | None, previous: datetime | None, timezone: str) -> datetime | None:
    if value is None:
        return None
    local_time = utc_naive_to_local(previous, timezone).time() if previous else time.min
    local = datetime.combine(date.fromisoformat(value), local_time, get_timezone(timezone))
    return local_to_utc_naive(local)


def validate_link(topic: ContentTopic, task: UserTask, session: Session) -> None:
    if task.category != "自媒体":
        raise ValueError("只能关联自媒体任务")
    existing = session.query(ContentTopic).filter(ContentTopic.task_id == task.id, ContentTopic.id != topic.id).first()
    if existing:
        raise ValueError("该任务已关联其他选题")
    if topic.task_id and topic.task_id != task.id:
        raise ValueError("选题已关联任务，不能覆盖现有关联")


def _log(topic: ContentTopic, task: UserTask, direction: str) -> None:
    logger.info("%s", json.dumps({"time": utc_isoformat(datetime.utcnow()), "level": "INFO",
        "agent": "sparkling", "event": "topic_task_sync_prepared", "msg": "选题任务联动已准备，等待事务提交",
        "trace": str(uuid4()), "data": {"topic_id": topic.id, "task_id": task.id,
        "direction": direction, "status": topic.status}}, ensure_ascii=False))


def sync_from_topic(topic: ContentTopic, session: Session, timezone: str) -> tuple[UserTask, bool, str | None] | None:
    task = session.get(UserTask, topic.task_id) if topic.task_id else None
    if topic.task_id and not task:
        raise ValueError("关联任务不存在")
    if topic.status == "published":
        topic.published_at = topic.published_at or datetime.utcnow()
        if topic.published_at > datetime.utcnow():
            raise ValueError("实际发布时间不能晚于当前时间")
    else:
        topic.published_at = None
    if task is None and topic.status == "working":
        task = UserTask(title=topic.title, description=topic.description, category="自媒体",
                        completed=False, board_status="doing", board_position=0)
        session.add(task)
        session.flush()
        topic.task_id = task.id
    if task is None:
        return None
    validate_link(topic, task, session)
    old_completed, old_actual = task.completed, task.actual_completion_date
    due = utc_naive_to_local(topic.scheduled_at, timezone).date().isoformat() if topic.scheduled_at else None
    actual = utc_naive_to_local(topic.published_at, timezone).date().isoformat() if topic.published_at else None
    completed = topic.status == "published"
    validate_task_dates(task.start_date, due, actual, completed, timezone)
    task.due_date = due
    task.actual_completion_date = actual
    if task.completed != completed:
        task.completed_at = datetime.utcnow() if completed else None
    task.completed = completed
    if topic.status == "working":
        task.board_status = "doing"
    elif topic.status == "not_started" and task.board_status == "doing":
        task.board_status = "backlog"
    task.updated_at = datetime.utcnow()
    _log(topic, task, "topic_to_task")
    return task, old_completed, old_actual


def sync_from_task(task: UserTask, session: Session, timezone: str, *, dates: bool = True, state: bool = True) -> None:
    topics = session.query(ContentTopic).filter(ContentTopic.task_id == task.id).all()
    if topics and task.category != "自媒体":
        raise ValueError("已关联选题的任务必须保留自媒体分类")
    if not dates and not state:
        return
    for topic in topics:
        if dates:
            topic.scheduled_at = date_at_local_time(task.due_date, topic.scheduled_at, timezone)
        if state:
            topic.status = "published" if task.completed else "working" if task.board_status == "doing" else "not_started"
        if state and task.completed:
            actual = task.actual_completion_date or (utc_naive_to_local(task.completed_at, timezone).date().isoformat() if task.completed_at else None)
            # 已有同日精确时间保持不变；新完成优先保留本次操作的时分。
            previous = topic.published_at or task.completed_at
            topic.published_at = date_at_local_time(actual, previous, timezone)
            if topic.published_at and topic.published_at > datetime.utcnow():
                topic.published_at = date_at_local_time(actual, None, timezone)
        elif state:
            topic.published_at = None
        topic.updated_at = datetime.utcnow()
        _log(topic, task, "task_to_topic")
