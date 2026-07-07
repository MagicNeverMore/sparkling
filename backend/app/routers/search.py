"""语义搜索路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import Settings, ThoughtAtom
from ..routers.atoms import AtomOut, _to_out
from ..services.memory.embedding import search_similar
from ..services.settings.settings_snapshot import snapshot_embedding_settings

router = APIRouter()
MAX_SEARCH_QUERY_CHARS = 2_000
logger = get_logger(__name__)


class SearchResult(BaseModel):
    atom: AtomOut
    score: float


@router.get("", response_model=list[SearchResult])
async def semantic_search(
    q: str = Query(..., min_length=1, max_length=MAX_SEARCH_QUERY_CHARS),
    k: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[SearchResult]:
    """语义搜索：embed 查询文本 → KNN → 返回相关想法列表。

    Settings 未配置 embed_dim/embed_model 时返回空列表。
    """
    settings = session.get(Settings, 1)
    if settings is None:
        logger.info("语义搜索跳过：settings 未初始化")
        return []

    settings_snapshot = snapshot_embedding_settings(settings)
    session.close()
    candidates = await search_similar(q, settings_snapshot, k=k)
    if not candidates:
        logger.debug("语义搜索无候选 query_len=%d k=%d", len(q), k)
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

    logger.info("语义搜索完成 query_len=%d k=%d results=%d", len(q), k, len(results))
    return results
