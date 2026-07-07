"""图谱数据路由：返回节点和边，供前端 React Flow 渲染。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import ThoughtAtom, ThoughtLink

router = APIRouter()
logger = get_logger(__name__)


class GraphNode(BaseModel):
    id: str
    content: str
    status: str


class GraphEdge(BaseModel):
    source: str       # from_atom_id
    target: str       # to_atom_id
    type: Optional[str]
    confidence: Optional[float]
    confirmed: bool   # user_confirmed


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@router.get("", response_model=GraphOut)
async def get_graph(session: Session = Depends(get_session)) -> GraphOut:
    """返回图谱数据：排除已删除的 atom 和用户已忽略的 link。"""
    atoms = (
        session.query(ThoughtAtom)
        .filter(ThoughtAtom.status != "deleted")
        .all()
    )
    links = (
        session.query(ThoughtLink)
        .filter(ThoughtLink.user_ignored.is_(False))
        .all()
    )

    # 有效 atom id 集合，用于过滤边（防止关联到已删除节点）
    valid_ids = {a.id for a in atoms}

    nodes = [GraphNode(id=a.id, content=a.content, status=a.status) for a in atoms]
    edges = [
        GraphEdge(
            source=lk.from_atom_id,
            target=lk.to_atom_id,
            type=lk.link_type,
            confidence=lk.confidence,
            confirmed=lk.user_confirmed,
        )
        for lk in links
        if lk.from_atom_id in valid_ids and lk.to_atom_id in valid_ids
    ]

    logger.debug("图谱数据已生成 nodes=%d edges=%d", len(nodes), len(edges))
    return GraphOut(nodes=nodes, edges=edges)
