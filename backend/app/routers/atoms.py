"""想法（ThoughtAtom）CRUD 路由。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import ThoughtAtom
from ..services import task_queue as tq
from ..services.ws_manager import manager

logger = get_logger(__name__)
router = APIRouter()


class AtomCreate(BaseModel):
    content: str


class AtomPatch(BaseModel):
    content: Optional[str] = None
    version: Optional[int] = None  # 传则做乐观锁校验


class AtomOut(BaseModel):
    id: str
    content: str
    content_type: str
    status: str
    version: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


def _to_out(atom: ThoughtAtom) -> AtomOut:
    return AtomOut(
        id=atom.id,
        content=atom.content,
        content_type=atom.content_type,
        status=atom.status,
        version=atom.version,
        created_at=atom.created_at.isoformat(),
        updated_at=atom.updated_at.isoformat(),
    )


@router.get("", response_model=list[AtomOut])
async def list_atoms(session: Session = Depends(get_session)) -> list[AtomOut]:
    """列出所有未删除的想法，按创建时间倒序。"""
    atoms = (
        session.query(ThoughtAtom)
        .filter(ThoughtAtom.status != "deleted")
        .order_by(ThoughtAtom.created_at.desc())
        .all()
    )
    return [_to_out(a) for a in atoms]


@router.post("", response_model=AtomOut, status_code=201)
async def create_atom(
    body: AtomCreate,
    session: Session = Depends(get_session),
) -> AtomOut:
    """创建想法，入队 embedding 任务，并广播 atom.created 事件。"""
    atom = ThoughtAtom(
        id=str(uuid.uuid4()),
        content=body.content,
        content_type="text",
        status="inbox",
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(atom)
    session.commit()
    session.refresh(atom)

    # 异步触发 embedding（不阻塞响应）
    tq.enqueue(session, "embed", {"atom_id": atom.id})

    out = _to_out(atom)
    logger.info("atom 已创建 id=%s", atom.id)
    await manager.broadcast("atom.created", out.model_dump())
    return out


@router.patch("/{atom_id}", response_model=AtomOut)
async def update_atom(
    atom_id: str,
    body: AtomPatch,
    session: Session = Depends(get_session),
) -> AtomOut:
    """更新想法内容，支持乐观锁校验（version 不匹配返回 409）。"""
    atom = session.get(ThoughtAtom, atom_id)
    if atom is None or atom.status == "deleted":
        raise HTTPException(status_code=404, detail="atom 不存在")

    # 乐观锁校验
    if body.version is not None and body.version != atom.version:
        raise HTTPException(
            status_code=409,
            detail=f"版本冲突：当前版本 {atom.version}，提交版本 {body.version}",
        )

    content_changed = False
    if body.content is not None and body.content != atom.content:
        atom.content = body.content
        atom.version += 1
        atom.updated_at = datetime.utcnow()
        content_changed = True

    session.commit()
    session.refresh(atom)

    if content_changed:
        # 内容变更，重新触发 embedding
        tq.enqueue(session, "embed", {"atom_id": atom.id})
        logger.info("atom 内容更新 id=%s version=%s", atom.id, atom.version)

    out = _to_out(atom)
    await manager.broadcast("atom.updated", out.model_dump())
    return out


@router.delete("/{atom_id}", status_code=204)
async def delete_atom(
    atom_id: str,
    session: Session = Depends(get_session),
) -> None:
    """软删除：将 status 置为 deleted，不物理删除记录。"""
    atom = session.get(ThoughtAtom, atom_id)
    if atom is None or atom.status == "deleted":
        raise HTTPException(status_code=404, detail="atom 不存在")

    atom.status = "deleted"
    atom.deleted_at = datetime.utcnow()
    atom.updated_at = datetime.utcnow()
    session.commit()
    logger.info("atom 已软删除 id=%s", atom.id)
    await manager.broadcast("atom.deleted", {"id": atom.id})
