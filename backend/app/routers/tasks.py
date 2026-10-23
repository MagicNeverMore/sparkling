"""用户任务 CRUD —— 自媒体发布计划、App 开发计划等。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import ContentTopic, UserTask
from ..services.task_dates import log_completion_change, validate_task_dates
from ..services.social_media.task_sync import sync_from_task
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
    completed: bool = False
    actual_completion_date: Optional[str] = None


class TaskPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    completed: Optional[bool] = None
    actual_completion_date: Optional[str] = None
    timezone: str = "UTC"


class TaskOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    category: Optional[str]
    start_date: Optional[str]
    due_date: Optional[str]
    completed: bool
    completed_at: Optional[str]
    actual_completion_date: Optional[str]
    board_status: str
    board_position: int
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
        actual_completion_date=task.actual_completion_date,
        board_status=task.board_status,
        board_position=task.board_position,
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
    if body.topic_id and (topic is None or topic.status == "published" or topic.task_id):
        raise HTTPException(status_code=422, detail="只能关联尚未发布且未关联任务的选题")
    try:
        timezone = get_timezone(body.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    due_date = body.due_date
    if topic and topic.scheduled_at and "due_date" not in body.model_fields_set:
        due_date = utc_naive_to_local(topic.scheduled_at, timezone.key).date().isoformat()
    actual = body.actual_completion_date
    if body.completed and actual is None:
        actual = datetime.now(timezone).date().isoformat()
    try:
        validate_task_dates(body.start_date, due_date, actual, body.completed, timezone.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task = UserTask(
        title=body.title,
        description=body.description,
        category=body.category,
        start_date=body.start_date,
        due_date=due_date,
        completed=body.completed,
        completed_at=datetime.utcnow() if body.completed else None,
        actual_completion_date=actual,
    )
    session.add(task)
    session.flush()
    if topic:
        task.board_status = "doing"
        topic.task_id = task.id
        topic.updated_at = datetime.utcnow()
        sync_from_task(task, session, body.timezone)
    session.commit()
    session.refresh(task)
    log_completion_change(task.id, False, task.completed, None, task.actual_completion_date)
    logger.info("任务已创建 task_id=%s category=%s due_date=%s", task.id, task.category, task.due_date)
    return _to_out(task)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, body: TaskPatch, session: Session = Depends(get_session)) -> TaskOut:
    task = session.get(UserTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    fields = body.model_fields_set
    old_completed, old_date = task.completed, task.actual_completion_date
    old_due = task.due_date
    completed = body.completed if body.completed is not None else task.completed
    start = body.start_date if "start_date" in fields else task.start_date
    due = body.due_date if "due_date" in fields else task.due_date
    actual = body.actual_completion_date if "actual_completion_date" in fields else old_date
    try:
        timezone = get_timezone(body.timezone)
        if not completed:
            if body.actual_completion_date is not None:
                raise ValueError("未完成任务不能填写实际完成日期")
            actual = None
        elif "actual_completion_date" not in fields and actual is None:
            actual = (utc_naive_to_local(task.completed_at, timezone.key).date().isoformat()
                      if task.completed and task.completed_at
                      else datetime.now(timezone).date().isoformat())
        validate_task_dates(start, due, actual, completed, timezone.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.category is not None:
        task.category = body.category
    task.start_date = start
    task.due_date = due
    task.actual_completion_date = actual

    # 切换完成状态时记录时间
    if body.completed is not None and body.completed != task.completed:
        task.completed = body.completed
        task.completed_at = datetime.utcnow() if body.completed else None
        logger.info("任务完成状态已变更 task_id=%s completed=%s", task.id, task.completed)

    task.updated_at = datetime.utcnow()
    try:
        sync_from_task(task, session, body.timezone, dates=old_due != task.due_date,
                       state=old_completed != task.completed or old_date != task.actual_completion_date)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    session.refresh(task)
    log_completion_change(task.id, old_completed, task.completed, old_date, actual)
    logger.info("任务已更新 task_id=%s", task.id)
    return _to_out(task)


class BoardMove(BaseModel):
    status: Literal["doing", "next", "backlog"]
    before_id: Optional[str] = None
    timezone: str = "UTC"


@router.patch("/board/{task_id}", response_model=list[TaskOut])
def move_board_task(task_id: str, body: BoardMove, session: Session = Depends(get_session)) -> list[TaskOut]:
    # 同一事务重排目标列，避免两个独立 PATCH 只保存了一半顺序。
    tasks = session.query(UserTask).order_by(UserTask.id).with_for_update().all()
    task = next((item for item in tasks if item.id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.completed:
        raise HTTPException(status_code=409, detail="已完成任务不在看板中，请先重新打开")
    if body.status == "backlog" and body.before_id:
        raise HTTPException(status_code=422, detail="待安排按截止日期自动排序")
    target = sorted((item for item in tasks if not item.completed and item.id != task_id
                     and item.board_status == body.status),
                    key=lambda item: (item.board_position, item.created_at, item.id))
    index = len(target)
    if body.before_id:
        index = next((i for i, item in enumerate(target) if item.id == body.before_id), -1)
        if index < 0:
            raise HTTPException(status_code=409, detail="目标任务已变化，请刷新后重试")
    previous = task.board_status
    try:
        get_timezone(body.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    task.board_status = body.status
    target.insert(index, task)
    now = datetime.utcnow()
    for position, item in enumerate(target):
        item.board_position = position
        item.updated_at = now
    try:
        sync_from_task(task, session, body.timezone, dates=False)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    logger.info("%s", json.dumps({"time": utc_isoformat(now), "level": "INFO", "agent": "sparkling",
        "event": "task_board_moved", "msg": "任务看板位置已更新", "trace": str(uuid4()),
        "data": {"task_id": task_id, "previous_status": previous, "status": body.status,
                 "before_id": body.before_id}}, ensure_ascii=False))
    return [_to_out(item) for item in tasks]


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
