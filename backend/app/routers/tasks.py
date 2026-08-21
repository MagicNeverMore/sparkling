"""用户任务 CRUD —— 自媒体发布计划、App 开发计划等。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import ContentTopic, UserTask
from ..time_utils import get_timezone, utc_isoformat, utc_naive_to_local

router = APIRouter()
logger = get_logger(__name__)


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[str] = None  # 'YYYY-MM-DD'
    due_date: Optional[str] = None   # 'YYYY-MM-DD'
    topic_id: Optional[str] = None
    timezone: str = "UTC"


class TaskPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    completed: Optional[bool] = None


class TaskOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    category: Optional[str]
    start_date: Optional[str]
    due_date: Optional[str]
    completed: bool
    completed_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


def _to_out(task: UserTask) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        category=task.category,
        start_date=task.start_date,
        due_date=task.due_date,
        completed=task.completed,
        completed_at=utc_isoformat(task.completed_at) if task.completed_at else None,
        created_at=utc_isoformat(task.created_at),
        updated_at=utc_isoformat(task.updated_at),
    )


@router.get("", response_model=list[TaskOut])
def list_tasks(session: Session = Depends(get_session)) -> list[TaskOut]:
    tasks = session.query(UserTask).order_by(UserTask.created_at.desc()).all()
    logger.debug("任务列表已读取 count=%d", len(tasks))
    return [_to_out(t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, session: Session = Depends(get_session)) -> TaskOut:
    if body.topic_id and body.category != "自媒体":
        raise HTTPException(status_code=422, detail="只有自媒体任务可以关联选题")
    topic = session.get(ContentTopic, body.topic_id) if body.topic_id else None
    if body.topic_id and (topic is None or topic.status != "not_started"):
        raise HTTPException(status_code=422, detail="只能关联未开始的选题")
    try:
        timezone = get_timezone(body.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    due_date = body.due_date
    if topic and topic.scheduled_at:
        due_date = utc_naive_to_local(topic.scheduled_at, timezone.key).date().isoformat()
    task = UserTask(
        title=body.title,
        description=body.description,
        category=body.category,
        start_date=body.start_date,
        due_date=due_date,
    )
    session.add(task)
    session.flush()
    if topic:
        topic.status = "working"
        topic.task_id = task.id
        topic.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(task)
    logger.info("任务已创建 task_id=%s category=%s due_date=%s", task.id, task.category, task.due_date)
    return _to_out(task)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, body: TaskPatch, session: Session = Depends(get_session)) -> TaskOut:
    task = session.get(UserTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.category is not None:
        task.category = body.category
    if body.start_date is not None:
        task.start_date = body.start_date
    if body.due_date is not None:
        task.due_date = body.due_date

    # 切换完成状态时记录时间
    if body.completed is not None and body.completed != task.completed:
        task.completed = body.completed
        task.completed_at = datetime.utcnow() if body.completed else None
        logger.info("任务完成状态已变更 task_id=%s completed=%s", task.id, task.completed)

    task.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(task)
    logger.info("任务已更新 task_id=%s", task.id)
    return _to_out(task)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, session: Session = Depends(get_session)) -> None:
    task = session.get(UserTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    linked_topics = session.query(ContentTopic).filter(ContentTopic.task_id == task_id).all()
    for topic in linked_topics:
        topic.task_id = None
        topic.updated_at = datetime.utcnow()
    session.delete(task)
    session.commit()
    logger.info("任务已删除 task_id=%s", task_id)
