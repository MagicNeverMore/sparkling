"""Trend 热点内容 API。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import TrendItem, TrendRun
from ..services.trend.collector import enqueue_trend_run
from ..time_utils import utc_isoformat

router = APIRouter()


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
    created_at: str
    updated_at: str


class TrendListOut(BaseModel):
    items: list[TrendItemOut]
    total: int


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
    query = session.query(TrendItem)
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
        if source_lower and source_lower not in sources:
            continue
        filtered.append(item)

    page = filtered[offset : offset + limit]
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
        return _to_run_out(active)
    run = enqueue_trend_run(session, "manual")
    return _to_run_out(run)


@router.get("/runs/latest", response_model=Optional[TrendRunOut])
def latest_trend_run(session: Session = Depends(get_session)) -> Optional[TrendRunOut]:
    run = session.query(TrendRun).order_by(TrendRun.created_at.desc()).first()
    return _to_run_out(run) if run else None


@router.get("/{trend_id}", response_model=TrendItemOut)
def get_trend(trend_id: str, session: Session = Depends(get_session)) -> TrendItemOut:
    item = session.get(TrendItem, trend_id)
    if not item:
        raise HTTPException(status_code=404, detail="Trend not found")
    return _to_item_out(item)
