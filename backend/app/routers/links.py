"""思想关联（ThoughtLink）路由：查询、确认、忽略。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import Settings, ThoughtAtom, ThoughtLink
from ..services.ws_manager import manager
from ..time_utils import utc_isoformat

router = APIRouter()
logger = get_logger(__name__)


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


class ManualLinkCreate(BaseModel):
    from_atom_id: str = Field(..., min_length=1, max_length=255)
    to_atom_id: str = Field(..., min_length=1, max_length=255)


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
        created_at=utc_isoformat(link.created_at),
    )


@router.get("", response_model=list[LinkOut])
async def list_links(session: Session = Depends(get_session)) -> list[LinkOut]:
    """列出所有未忽略且两端 atom 均有效的关联（含已确认和待确认）。"""
    settings = session.get(Settings, 1)
    suggest_threshold = settings.link_threshold_suggest if settings else 0.70
    valid_atom_ids = {
        atom_id
        for (atom_id,) in (
            session.query(ThoughtAtom.id)
            .filter(ThoughtAtom.status != "deleted")
            .all()
        )
    }
    links = (
        session.query(ThoughtLink)
        .filter(ThoughtLink.user_ignored.is_(False))
        .order_by(ThoughtLink.created_at.desc())
        .all()
    )
    visible_links = [
        _to_out(lk)
        for lk in links
        if lk.from_atom_id in valid_atom_ids and lk.to_atom_id in valid_atom_ids
        and (lk.source == "user" or (lk.confidence is not None and lk.confidence >= suggest_threshold))
    ]
    logger.debug(
        "关联列表已生成 total=%d visible=%d suggest_threshold=%.3f",
        len(links),
        len(visible_links),
        suggest_threshold,
    )
    return visible_links


@router.post("", response_model=LinkOut)
async def create_manual_link(
    body: ManualLinkCreate,
    session: Session = Depends(get_session),
) -> LinkOut:
    """通过 atom UUID 手动建立关联；已有边会被恢复并确认为用户关联。"""
    from_atom_id = body.from_atom_id.strip()
    to_atom_id = body.to_atom_id.strip()
    if from_atom_id == to_atom_id:
        raise HTTPException(status_code=400, detail="不能将 atom 与自身关联")

    atoms = {
        atom.id: atom
        for atom in (
            session.query(ThoughtAtom)
            .filter(ThoughtAtom.id.in_([from_atom_id, to_atom_id]))
            .all()
        )
    }
    if from_atom_id not in atoms or atoms[from_atom_id].status == "deleted":
        raise HTTPException(status_code=404, detail="来源 atom 不存在")
    if to_atom_id not in atoms or atoms[to_atom_id].status == "deleted":
        raise HTTPException(status_code=404, detail="目标 atom 不存在")

    link = (
        session.query(ThoughtLink)
        .filter(
            or_(
                and_(
                    ThoughtLink.from_atom_id == from_atom_id,
                    ThoughtLink.to_atom_id == to_atom_id,
                ),
                and_(
                    ThoughtLink.from_atom_id == to_atom_id,
                    ThoughtLink.to_atom_id == from_atom_id,
                ),
            )
        )
        .order_by(ThoughtLink.created_at.desc())
        .first()
    )
    if link is None:
        # 固定端点顺序，避免同一条无向边被反向重复创建。
        first_id, second_id = sorted((from_atom_id, to_atom_id))
        link = ThoughtLink(
            from_atom_id=first_id,
            to_atom_id=second_id,
            link_type="manual",
            confidence=None,
            source="user",
            user_confirmed=True,
            user_ignored=False,
        )
        session.add(link)
    else:
        link.source = "user"
        link.user_confirmed = True
        link.user_ignored = False

    session.commit()
    session.refresh(link)
    out = _to_out(link)
    logger.info(
        "手动关联已建立 link_id=%s from=%s to=%s",
        link.id,
        link.from_atom_id,
        link.to_atom_id,
    )
    session.close()
    await manager.broadcast("link.created", out.model_dump())
    return out


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
    link.source = "user"
    session.commit()

    out = _to_out(link)
    logger.info("关联已确认 link_id=%s from=%s to=%s", link.id, link.from_atom_id, link.to_atom_id)
    session.close()
    await manager.broadcast("link.confirmed", out.model_dump())
    return out


@router.post("/{link_id}/ignore", response_model=LinkOut)
async def ignore_link(
    link_id: str,
    session: Session = Depends(get_session),
) -> LinkOut:
    """忽略或取消关联。"""
    link = session.get(ThoughtLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="link 不存在")

    link.user_ignored = True
    link.user_confirmed = False
    session.commit()
    out = _to_out(link)
    link_id_for_event = link.id
    logger.info("关联已忽略 link_id=%s from=%s to=%s", link.id, link.from_atom_id, link.to_atom_id)
    session.close()
    await manager.broadcast("link.ignored", {"id": link_id_for_event})

    return out
