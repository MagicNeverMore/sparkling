"""用户任务 CRUD —— 自媒体发布计划、App 开发计划等。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import UserTask
from ..time_utils import utc_isoformat

router = APIRouter()


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[str] = None  # 'YYYY-MM-DD'
    due_date: Optional[str] = None   # 'YYYY-MM-DD'


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
    return [_to_out(t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, session: Session = Depends(get_session)) -> TaskOut:
    task = UserTask(
        title=body.title,
        description=body.description,
        category=body.category,
        start_date=body.start_date,
        due_date=body.due_date,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
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

    task.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(task)
    return _to_out(task)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, session: Session = Depends(get_session)) -> None:
    task = session.get(UserTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    session.delete(task)
    session.commit()
