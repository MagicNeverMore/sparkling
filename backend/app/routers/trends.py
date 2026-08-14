"""Trend 热点内容 API。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_session
from ..logger import get_logger
from ..models import TrendItem, TrendRun
from ..services.trend.collector import enqueue_trend_run
from ..time_utils import utc_isoformat

router = APIRouter()
logger = get_logger(__name__)


class TrendResourceOut(BaseModel):
    title: str
    url: str
    source: str


class TrendItemOut(BaseModel):
    id: str
    title: str
    category: Optional[str]
    score: float
    scoring_reason: Optional[str]
    core_insight: Optional[str]
    content: Optional[str]
    tags: list[str]
    resources: list[TrendResourceOut]
    first_seen_at: str
    last_seen_at: str
    is_favorited: bool
    favorited_at: Optional[str]
    created_at: str
    updated_at: str


class TrendListOut(BaseModel):
    items: list[TrendItemOut]
    total: int


class TrendFavoriteUpdate(BaseModel):
    is_favorited: bool


class TrendBulkDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


class TrendBulkDeleteOut(BaseModel):
    deleted_count: int
    deleted_ids: list[str]


class TrendRunOut(BaseModel):
    id: str
    trigger: str
    status: str
    error: Optional[str]
    candidate_count: int
    saved_count: int
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str
    updated_at: str


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _to_item_out(item: TrendItem) -> TrendItemOut:
    resources = []
    for resource in _json_list(item.resources_json):
        if not isinstance(resource, dict):
            continue
        resources.append(
            TrendResourceOut(
                title=str(resource.get("title") or resource.get("url") or ""),
                url=str(resource.get("url") or ""),
                source=str(resource.get("source") or "web"),
            )
        )
    tags = [str(tag) for tag in _json_list(item.tags_json) if str(tag)]
    return TrendItemOut(
        id=item.id,
        title=item.title,
        category=item.category,
        score=item.score,
        scoring_reason=item.scoring_reason,
        core_insight=item.core_insight,
        content=item.content,
        tags=tags,
        resources=resources,
        first_seen_at=utc_isoformat(item.first_seen_at),
        last_seen_at=utc_isoformat(item.last_seen_at),
        is_favorited=item.is_favorited,
        favorited_at=utc_isoformat(item.favorited_at) if item.favorited_at else None,
        created_at=utc_isoformat(item.created_at),
        updated_at=utc_isoformat(item.updated_at),
    )


def _to_run_out(run: TrendRun) -> TrendRunOut:
    return TrendRunOut(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        error=run.error,
        candidate_count=run.candidate_count,
        saved_count=run.saved_count,
        started_at=utc_isoformat(run.started_at) if run.started_at else None,
        finished_at=utc_isoformat(run.finished_at) if run.finished_at else None,
        created_at=utc_isoformat(run.created_at),
        updated_at=utc_isoformat(run.updated_at),
    )


@router.get("", response_model=TrendListOut)
def list_trends(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> TrendListOut:
    query = session.query(TrendItem).filter(TrendItem.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                TrendItem.title.ilike(like),
                TrendItem.category.ilike(like),
                TrendItem.core_insight.ilike(like),
                TrendItem.content.ilike(like),
            )
        )
    if category:
        query = query.filter(TrendItem.category == category)

    ordered = query.order_by(TrendItem.last_seen_at.desc()).all()
    filtered: list[TrendItem] = []
    tag_lower = tag.lower() if tag else None
    source_lower = source.lower() if source else None
    for item in ordered:
        tags = [str(value).lower() for value in _json_list(item.tags_json)]
        resources = _json_list(item.resources_json)
        sources = [
            str(resource.get("source") or "").lower()
            for resource in resources
            if isinstance(resource, dict)
        ]
        if tag_lower and tag_lower not in tags:
            continue
        source_matches = source_lower is None or any(
            value == source_lower or (source_lower == "rss" and value.startswith("rss:"))
            for value in sources
        )
        if not source_matches:
            continue
        filtered.append(item)

    page = filtered[offset : offset + limit]
    logger.debug(
        "Trend 列表已读取 total=%d page=%d limit=%d offset=%d",
        len(filtered),
        len(page),
        limit,
        offset,
    )
    return TrendListOut(items=[_to_item_out(item) for item in page], total=len(filtered))


@router.post("/run", response_model=TrendRunOut, status_code=202)
def run_trend_collection(session: Session = Depends(get_session)) -> TrendRunOut:
    active = (
        session.query(TrendRun)
        .filter(TrendRun.status.in_(["pending", "running"]))
        .order_by(TrendRun.created_at.desc())
        .first()
    )
    if active:
        logger.info("Trend 采集已有运行中任务 run_id=%s status=%s", active.id, active.status)
        return _to_run_out(active)
    run = enqueue_trend_run(session, "manual")
    logger.info("Trend 手动采集已入队 run_id=%s", run.id)
    return _to_run_out(run)


@router.get("/runs/latest", response_model=Optional[TrendRunOut])
def latest_trend_run(session: Session = Depends(get_session)) -> Optional[TrendRunOut]:
    run = session.query(TrendRun).order_by(TrendRun.created_at.desc()).first()
    logger.debug("读取最新 Trend run found=%s", run is not None)
    return _to_run_out(run) if run else None


@router.put("/{trend_id}/favorite", response_model=TrendItemOut)
def update_trend_favorite(
    trend_id: str,
    body: TrendFavoriteUpdate,
    session: Session = Depends(get_session),
) -> TrendItemOut:
    item = session.get(TrendItem, trend_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Trend not found")
    now = datetime.utcnow()
    item.is_favorited = body.is_favorited
    item.favorited_at = now if body.is_favorited else None
    item.updated_at = now
    session.commit()
    session.refresh(item)
    logger.info("Trend 收藏状态已更新 trend_id=%s is_favorited=%s", trend_id, item.is_favorited)
    return _to_item_out(item)


@router.post("/bulk-delete", response_model=TrendBulkDeleteOut)
def bulk_delete_trends(
    body: TrendBulkDeleteRequest,
    session: Session = Depends(get_session),
) -> TrendBulkDeleteOut:
    ids = list(dict.fromkeys(body.ids))
    items = (
        session.query(TrendItem)
        .filter(TrendItem.id.in_(ids))
        .filter(TrendItem.deleted_at.is_(None))
        .all()
    )
    now = datetime.utcnow()
    deleted_ids = [item.id for item in items]
    for item in items:
        item.deleted_at = now
        item.updated_at = now
    session.commit()
    logger.info(
        "Trend 批量软删除完成 requested=%d deleted=%d",
        len(ids),
        len(deleted_ids),
    )
    return TrendBulkDeleteOut(deleted_count=len(deleted_ids), deleted_ids=deleted_ids)


@router.get("/{trend_id}", response_model=TrendItemOut)
def get_trend(trend_id: str, session: Session = Depends(get_session)) -> TrendItemOut:
    item = session.get(TrendItem, trend_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Trend not found")
    logger.debug("读取 Trend 详情 trend_id=%s", trend_id)
    return _to_item_out(item)


@router.delete("/{trend_id}", status_code=204)
def delete_trend(trend_id: str, session: Session = Depends(get_session)) -> Response:
    item = session.get(TrendItem, trend_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Trend not found")
    now = datetime.utcnow()
    item.deleted_at = now
    item.updated_at = now
    session.commit()
    logger.info("Trend 已软删除 trend_id=%s", trend_id)
    return Response(status_code=204)
