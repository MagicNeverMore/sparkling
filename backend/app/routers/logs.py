"""Settings Logs：浏览统一轮转日志。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services.settings.log_reader import read_log_page

router = APIRouter()


class LogFileOut(BaseModel):
    name: str
    size_bytes: int
    modified_at: str


class LogEntryOut(BaseModel):
    line_number: int
    text: str


class LogPageOut(BaseModel):
    file: Optional[str]
    files: list[LogFileOut]
    total_matches: int
    next_before: Optional[int]
    items: list[LogEntryOut]


@router.get("", response_model=LogPageOut)
def get_logs(
    file: Optional[str] = Query(default=None, max_length=100),
    level: Optional[str] = Query(default=None, max_length=20),
    query: Optional[str] = Query(default=None, max_length=200),
    before: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=20, le=500),
) -> LogPageOut:
    try:
        return LogPageOut.model_validate(
            read_log_page(
                file_name=file,
                level=level,
                query=query,
                before=before,
                limit=limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
