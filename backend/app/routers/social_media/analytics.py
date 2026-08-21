"""Social Media Analysis：设置、YouTube OAuth、日级同步与最新完整 List。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...config import config as app_config
from ...db import get_session
from ...logger import get_logger
from ...models import SocialMediaSyncRun, SocialMediaVideo, SocialMediaVideoMetric, TaskQueue
from ...services.social_media.collector import (
    SOCIAL_MEDIA_RUN_TIMEOUT_SECONDS,
    calculate_next_run_at,
    enqueue_social_media_task,
)
from ...services.social_media.config import (
    disconnect_youtube,
    load_social_media_config,
    update_social_media_config,
)
from ...services.social_media.youtube import build_oauth_url, exchange_oauth_code, oauth_trace_id
from ...services.settings.deployment_config import load_deployment_config
from ...services.settings import runtime_config
from ...time_utils import get_timezone, utc_isoformat

router = APIRouter()
logger = get_logger(__name__)


def _oauth_runtime_context() -> tuple[str, str]:
    """用于判断 callback 与 status 是否落在同一容器和 control DB。"""
    return os.getenv("HOSTNAME", "local"), str(runtime_config.CONTROL_DB_PATH)


class SocialMediaSettingsUpdate(BaseModel):
    schedule_enabled: Optional[bool] = None
    update_frequency: Optional[str] = None
    schedule_time: Optional[str] = None
    timezone: Optional[str] = None
    youtube_client_id: Optional[str] = None
    youtube_client_secret: Optional[str] = None

    @field_validator("update_frequency")
    @classmethod
    def validate_frequency(cls, value: str | None) -> str | None:
        if value is not None and value not in {"hourly", "manual"}:
            raise ValueError("update_frequency must be hourly or manual")
        return value

    @field_validator("schedule_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            hour, minute = (int(part) for part in value.split(":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("schedule_time must be HH:MM") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("schedule_time must be HH:MM")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            get_timezone(value)
        return value


class SocialMediaSettingsOut(BaseModel):
    schedule_enabled: bool
    update_frequency: str
    schedule_time: str
    timezone: str
    youtube_client_id: Optional[str]
    youtube_client_secret_masked: Optional[str]
    youtube_connected: bool
    youtube_channel_id: Optional[str]
    youtube_channel_title: Optional[str]
    last_run_at: Optional[str]
    next_run_at: Optional[str]


class OAuthUrlOut(BaseModel):
    authorization_url: str


class SocialMediaRunOut(BaseModel):
    id: str
    trigger: Literal["manual", "scheduled", "recovered"]
    status: Literal["running", "done", "failed"]
    metric_date: Optional[str]
    video_count: int
    error: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str


class SocialMediaSyncRequestOut(BaseModel):
    task_id: str
    trigger: Literal["manual"]
    status: Literal["queued"]


class SocialMediaVideoOut(BaseModel):
    id: str
    external_video_id: str
    title: str
    published_at: str
    platform: str
    duration_seconds: int


class SocialMediaVideoListOut(BaseModel):
    total: int
    items: list[SocialMediaVideoOut]


class SocialMediaVideoMetricOut(BaseModel):
    video_id: str
    ctr: Optional[float]
    average_view_duration_seconds: Optional[float]
    average_view_percentage: Optional[float]
    views: int
    subscribers_gained: int
    subscribers_lost: int
    net_subscribers: int


class SocialMediaMetricListOut(BaseModel):
    data_date: Optional[str]
    updated_at: Optional[str]
    items: list[SocialMediaVideoMetricOut]


def _masked(value: str | None) -> str | None:
    if not value:
        return None
    return f"••••{value[-4:]}" if len(value) > 4 else "••••"


def _youtube_oauth_redirect_uri(request: Request) -> str:
    """生产使用 control DB 中的公开 origin；开发环境允许 dev origin。"""
    callback_path = request.app.url_path_for("youtube_oauth_callback")
    public_origin = load_deployment_config().public_origin
    if public_origin:
        return f"{public_origin}{callback_path}"
    dev_origin = app_config.dev_origin.rstrip("/")
    if dev_origin:
        return f"{dev_origin}{callback_path}"
    raise ValueError("请先在 Settings → Network / Deployment 配置 Public URL")


def _oauth_frontend_origin(request: Request, redirect_uri: str | None) -> str:
    if redirect_uri:
        parsed = urlsplit(redirect_uri)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return str(request.base_url).rstrip("/")


def _settings_out() -> SocialMediaSettingsOut:
    config = load_social_media_config()
    instance_id, control_db = _oauth_runtime_context()
    logger.info(
        "social_media.connection.status_read youtube_connected=%s refresh_credential_present=%s "
        "has_channel_id=%s channel_id=%s instance_id=%s control_db=%s",
        config.youtube_connected,
        bool(config.youtube_refresh_token),
        bool(config.youtube_channel_id),
        config.youtube_channel_id,
        instance_id,
        control_db,
    )
    return SocialMediaSettingsOut(
        schedule_enabled=config.schedule_enabled,
        update_frequency=config.update_frequency,
        schedule_time=config.schedule_time,
        timezone=config.timezone,
        youtube_client_id=config.youtube_client_id,
        youtube_client_secret_masked=_masked(config.youtube_client_secret),
        youtube_connected=config.youtube_connected,
        youtube_channel_id=config.youtube_channel_id,
        youtube_channel_title=config.youtube_channel_title,
        last_run_at=config.last_run_at,
        next_run_at=config.next_run_at,
    )


def _run_out(run: SocialMediaSyncRun) -> SocialMediaRunOut:
    return SocialMediaRunOut(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        metric_date=run.metric_date,
        video_count=run.video_count,
        error=run.error,
        started_at=utc_isoformat(run.started_at) if run.started_at else None,
        finished_at=utc_isoformat(run.finished_at) if run.finished_at else None,
        created_at=utc_isoformat(run.created_at),
    )


@router.get("/settings", response_model=SocialMediaSettingsOut)
def get_social_media_settings() -> SocialMediaSettingsOut:
    return _settings_out()


@router.put("/settings", response_model=SocialMediaSettingsOut)
def update_social_media_settings(body: SocialMediaSettingsUpdate) -> SocialMediaSettingsOut:
    current = load_social_media_config()
    fields: dict[str, object] = {}
    for name in ("schedule_enabled", "update_frequency", "schedule_time", "timezone", "youtube_client_id"):
        if name in body.model_fields_set:
            fields[name] = getattr(body, name)
    if "youtube_client_secret" in body.model_fields_set:
        fields["youtube_client_secret"] = body.youtube_client_secret or None
    effective_enabled = bool(fields.get("schedule_enabled", current.schedule_enabled))
    effective_frequency = str(fields.get("update_frequency", current.update_frequency))
    effective_time = str(fields.get("schedule_time", current.schedule_time))
    effective_timezone = str(fields.get("timezone", current.timezone))
    fields["next_run_at"] = (
        utc_isoformat(calculate_next_run_at(effective_frequency, effective_time, effective_timezone))
        if effective_enabled and effective_frequency != "manual" and current.youtube_connected
        else None
    )
    update_social_media_config(**fields)
    logger.info(
        "social_media.settings.updated fields=%s",
        sorted(name for name in fields if name not in {"youtube_client_secret"}),
    )
    return _settings_out()


@router.get("/youtube/oauth/start", response_model=OAuthUrlOut)
def start_youtube_oauth(request: Request) -> OAuthUrlOut:
    config = load_social_media_config()
    try:
        redirect_uri = _youtube_oauth_redirect_uri(request)
        instance_id, control_db = _oauth_runtime_context()
        logger.info(
            "social_media.oauth.start redirect_uri=%s client_configured=%s request_host=%s "
            "forwarded_host=%s instance_id=%s control_db=%s",
            redirect_uri,
            bool(config.youtube_client_id and config.youtube_client_secret),
            request.headers.get("host"),
            request.headers.get("x-forwarded-host"),
            instance_id,
            control_db,
        )
        return OAuthUrlOut(authorization_url=build_oauth_url(config, redirect_uri))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/youtube/oauth/callback", name="youtube_oauth_callback")
async def youtube_oauth_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):  # noqa: ANN201
    config = load_social_media_config()
    trace_id = oauth_trace_id(state)
    instance_id, control_db = _oauth_runtime_context()
    frontend_origin = _oauth_frontend_origin(request, config.oauth_redirect_uri)
    frontend = f"{frontend_origin}/settings?section=social-media"
    if error or not code or not state:
        logger.warning(
            "social_media.oauth.callback.rejected trace_id=%s google_error=%s has_code=%s "
            "has_state=%s instance_id=%s control_db=%s",
            trace_id,
            error,
            bool(code),
            bool(state),
            instance_id,
            control_db,
        )
        return RedirectResponse(f"{frontend}&youtube=error")
    logger.info(
        "social_media.oauth.callback.received trace_id=%s stored_trace_id=%s state_match=%s "
        "redirect_uri=%s request_host=%s forwarded_host=%s instance_id=%s control_db=%s",
        trace_id,
        oauth_trace_id(config.oauth_state),
        bool(config.oauth_state and config.oauth_state == state),
        config.oauth_redirect_uri,
        request.headers.get("host"),
        request.headers.get("x-forwarded-host"),
        instance_id,
        control_db,
    )
    try:
        refresh_token, channel_id, channel_title = await exchange_oauth_code(config, code, state)
        next_run = (
            utc_isoformat(
                calculate_next_run_at(config.update_frequency, config.schedule_time, config.timezone)
            )
            if config.schedule_enabled and config.update_frequency != "manual"
            else None
        )
        saved = update_social_media_config(
            youtube_refresh_token=refresh_token,
            youtube_channel_id=channel_id,
            youtube_channel_title=channel_title,
            oauth_state=None,
            oauth_redirect_uri=None,
            next_run_at=next_run,
        )
        verified = load_social_media_config()
        persistence_matches = bool(
            saved.youtube_connected
            and verified.youtube_connected
            and saved.youtube_channel_id == channel_id
            and verified.youtube_channel_id == channel_id
        )
        if not persistence_matches:
            logger.error(
                "social_media.oauth.callback.persistence_mismatch trace_id=%s "
                "saved_connected=%s verified_connected=%s saved_channel_id=%s "
                "verified_channel_id=%s expected_channel_id=%s instance_id=%s control_db=%s",
                trace_id,
                saved.youtube_connected,
                verified.youtube_connected,
                saved.youtube_channel_id,
                verified.youtube_channel_id,
                channel_id,
                instance_id,
                control_db,
            )
            raise RuntimeError("YouTube 连接信息写入后校验失败")
    except Exception as exc:
        logger.exception("YouTube OAuth callback 失败: %s", exc)
        return RedirectResponse(f"{frontend}&youtube=error")
    logger.info(
        "social_media.oauth.callback.connected trace_id=%s channel_id=%s channel_title=%s "
        "instance_id=%s control_db=%s",
        trace_id,
        channel_id,
        channel_title,
        instance_id,
        control_db,
    )
    return RedirectResponse(f"{frontend}&youtube=connected")


@router.post("/youtube/disconnect", response_model=SocialMediaSettingsOut)
def disconnect_youtube_account() -> SocialMediaSettingsOut:
    current = load_social_media_config()
    disconnect_youtube()
    logger.info("social_media.oauth.disconnected channel_id=%s", current.youtube_channel_id)
    return _settings_out()


@router.post("/sync", response_model=SocialMediaSyncRequestOut, status_code=202)
def run_social_media_sync(session: Session = Depends(get_session)) -> SocialMediaSyncRequestOut:
    config = load_social_media_config()
    if not config.youtube_connected:
        raise HTTPException(status_code=400, detail="请先在 Social Media Settings 连接 YouTube")
    task = enqueue_social_media_task(session, "manual")
    logger.info(
        "social_media.sync.manual_requested task_id=%s task_status=%s channel_id=%s",
        task.id,
        task.status,
        config.youtube_channel_id,
    )
    return SocialMediaSyncRequestOut(task_id=task.id, trigger="manual", status="queued")


@router.get("/runs/latest", response_model=Optional[SocialMediaRunOut])
def latest_social_media_run(session: Session = Depends(get_session)) -> Optional[SocialMediaRunOut]:
    _expire_timed_out_social_media_runs(session)
    run = session.query(SocialMediaSyncRun).order_by(SocialMediaSyncRun.created_at.desc()).first()
    return _run_out(run) if run else None


def _expire_timed_out_social_media_runs(session: Session) -> None:
    """读取状态时也执行超时兜底，避免 worker 异常退出后 UI 永久显示同步中。"""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=SOCIAL_MEDIA_RUN_TIMEOUT_SECONDS)
    runs = (
        session.query(SocialMediaSyncRun)
        .filter(SocialMediaSyncRun.status == "running")
        .filter(SocialMediaSyncRun.started_at.is_not(None))
        .filter(SocialMediaSyncRun.started_at <= cutoff)
        .all()
    )
    if not runs:
        return
    for run in runs:
        error = f"任务执行超时（>{SOCIAL_MEDIA_RUN_TIMEOUT_SECONDS}s）"
        run.status = "failed"
        run.finished_at = now
        run.error = error
        run.updated_at = now
        task = (
            session.query(TaskQueue)
            .filter(TaskQueue.task_type == "social_media_collect")
            .filter(TaskQueue.status == "running")
            .filter(TaskQueue.payload.contains(run.id))
            .one_or_none()
        )
        if task is not None:
            task.status = "failed"
            task.last_error = error
            task.locked_by = None
            task.locked_at = None
            task.lease_until = None
            task.updated_at = now
        logger.error(
            "social_media.sync.timeout_reconciled run_id=%s task_id=%s timeout_seconds=%s",
            run.id,
            task.id if task is not None else None,
            SOCIAL_MEDIA_RUN_TIMEOUT_SECONDS,
        )
    session.commit()


@router.get("/videos", response_model=SocialMediaVideoListOut)
def list_social_media_videos(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    video_id: str | None = Query(default=None),
    title: str | None = Query(default=None),
    published_from: datetime | None = Query(default=None),
    published_to: datetime | None = Query(default=None),
    platform: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> SocialMediaVideoListOut:
    query = session.query(SocialMediaVideo)
    if video_id:
        query = query.filter(SocialMediaVideo.external_video_id == video_id)
    if title:
        query = query.filter(SocialMediaVideo.title.ilike(f"%{title}%"))
    if published_from:
        query = query.filter(SocialMediaVideo.published_at >= published_from)
    if published_to:
        query = query.filter(SocialMediaVideo.published_at <= published_to)
    if platform:
        query = query.filter(SocialMediaVideo.platform == platform)
    total = query.count()
    page = query.order_by(SocialMediaVideo.published_at.desc()).offset(offset).limit(limit).all()
    return SocialMediaVideoListOut(
        total=total,
        items=[
            SocialMediaVideoOut(
                id=item.id,
                external_video_id=item.external_video_id,
                title=item.title,
                published_at=utc_isoformat(item.published_at),
                platform=item.platform,
                duration_seconds=item.duration_seconds,
            )
            for item in page
        ],
    )


@router.get("/video-metrics", response_model=SocialMediaMetricListOut)
def list_latest_social_media_video_metrics(
    session: Session = Depends(get_session),
) -> SocialMediaMetricListOut:
    data_date = session.query(func.max(SocialMediaVideoMetric.data_date)).scalar()
    if data_date is None:
        return SocialMediaMetricListOut(data_date=None, updated_at=None, items=[])
    items = session.query(SocialMediaVideoMetric).filter_by(data_date=data_date).all()
    updated_at = max((item.updated_at for item in items), default=None)
    return SocialMediaMetricListOut(
        data_date=data_date,
        updated_at=utc_isoformat(updated_at) if updated_at else None,
        items=[
            SocialMediaVideoMetricOut(
                video_id=item.video_id,
                ctr=item.ctr,
                average_view_duration_seconds=item.average_view_duration_seconds,
                average_view_percentage=item.average_view_percentage,
                views=item.views,
                subscribers_gained=item.subscribers_gained,
                subscribers_lost=item.subscribers_lost,
                net_subscribers=item.net_subscribers,
            )
            for item in items
        ],
    )
