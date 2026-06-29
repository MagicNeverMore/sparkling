"""思想关联（ThoughtLink）路由：查询、确认、忽略。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import ThoughtLink
from ..services.ws_manager import manager

router = APIRouter()


class LinkOut(BaseModel):
    id: str
    from_atom_id: str
    to_atom_id: str
    link_type: Optional[str]
    confidence: Optional[float]
    source: str
    user_confirmed: bool
    user_ignored: bool
    created_at: str

    model_config = {"from_attributes": True}


def _to_out(link: ThoughtLink) -> LinkOut:
    return LinkOut(
        id=link.id,
        from_atom_id=link.from_atom_id,
        to_atom_id=link.to_atom_id,
        link_type=link.link_type,
        confidence=link.confidence,
        source=link.source,
        user_confirmed=link.user_confirmed,
        user_ignored=link.user_ignored,
        created_at=link.created_at.isoformat(),
    )


@router.get("", response_model=list[LinkOut])
async def list_links(session: Session = Depends(get_session)) -> list[LinkOut]:
    """列出所有未忽略的关联（含已确认和待确认）。"""
    links = (
        session.query(ThoughtLink)
        .filter(ThoughtLink.user_ignored.is_(False))
        .order_by(ThoughtLink.created_at.desc())
        .all()
    )
    return [_to_out(lk) for lk in links]


@router.post("/{link_id}/confirm", response_model=LinkOut)
async def confirm_link(
    link_id: str,
    session: Session = Depends(get_session),
) -> LinkOut:
    """确认 AI 建议的关联，广播 link.confirmed 事件。"""
    link = session.get(ThoughtLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="link 不存在")

    link.user_confirmed = True
    link.user_ignored = False
    session.commit()

    out = _to_out(link)
    await manager.broadcast("link.confirmed", out.model_dump())
    return out


@router.post("/{link_id}/ignore", response_model=LinkOut)
async def ignore_link(
    link_id: str,
    session: Session = Depends(get_session),
) -> LinkOut:
    """忽略 AI 建议的关联。"""
    link = session.get(ThoughtLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="link 不存在")

    link.user_ignored = True
    link.user_confirmed = False
    session.commit()

    return _to_out(link)
