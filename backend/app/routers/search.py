"""语义搜索路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Settings, ThoughtAtom
from ..routers.atoms import AtomOut, _to_out
from ..services.embedding import search_similar

router = APIRouter()


class SearchResult(BaseModel):
    atom: AtomOut
    score: float


@router.get("", response_model=list[SearchResult])
async def semantic_search(
    q: str = Query(..., min_length=1),
    k: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[SearchResult]:
    """语义搜索：embed 查询文本 → KNN → 返回相关想法列表。

    Settings 未配置 embed_dim/embed_model 时返回空列表。
    """
    settings = session.get(Settings, 1)
    if settings is None:
        return []

    candidates = await search_similar(session, q, settings, k=k)
    if not candidates:
        return []

    # 批量查询 atom 详情
    atom_ids = [atom_id for atom_id, _ in candidates]
    atoms_map = {
        a.id: a
        for a in session.query(ThoughtAtom).filter(ThoughtAtom.id.in_(atom_ids)).all()
    }

    results = []
    for atom_id, score in candidates:
        atom = atoms_map.get(atom_id)
        if atom and atom.status != "deleted":
            results.append(SearchResult(atom=_to_out(atom), score=score))

    return results
