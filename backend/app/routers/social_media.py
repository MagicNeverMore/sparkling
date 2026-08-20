"""Social Media Analysis：设置、YouTube OAuth、日级同步与最新完整 List。"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..config import config as app_config
from ..db import get_session
from ..logger import get_logger
from ..models import SocialMediaDataset, SocialMediaSyncRun, SocialMediaVideoSnapshot
from ..services.social_media.collector import (
    calculate_next_run_at,
    enqueue_social_media_run,
)
from ..services.social_media.config import (
    disconnect_youtube,
    load_social_media_config,
    update_social_media_config,
)
from ..services.social_media.youtube import build_oauth_url, exchange_oauth_code
from ..services.settings.deployment_config import load_deployment_config
from ..time_utils import get_timezone, utc_isoformat

router = APIRouter()
logger = get_logger(__name__)


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
    trigger: str
    status: str
    metric_date: Optional[str]
    video_count: int
    error: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str


class SocialMediaVideoOut(BaseModel):
    id: str
    external_video_id: str
    title: str
    published_at: str
    platform: str
    ctr: Optional[float]
    average_view_duration_seconds: Optional[float]
    average_view_percentage: Optional[float]
    duration_seconds: int
    views: int
    subscribers_gained: int
    subscribers_lost: int
    net_subscribers: int


class SocialMediaListOut(BaseModel):
    metric_date: Optional[str]
    collected_at: Optional[str]
    total: int
    items: list[SocialMediaVideoOut]


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
        logger.info(
            "social_media.oauth.start redirect_uri=%s client_configured=%s",
            redirect_uri,
            bool(config.youtube_client_id and config.youtube_client_secret),
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
    frontend_origin = _oauth_frontend_origin(request, config.oauth_redirect_uri)
    frontend = f"{frontend_origin}/settings?section=social-media"
    if error or not code or not state:
        logger.warning(
            "social_media.oauth.callback.rejected google_error=%s has_code=%s has_state=%s",
            error,
            bool(code),
            bool(state),
        )
        return RedirectResponse(f"{frontend}&youtube=error")
    logger.info("social_media.oauth.callback.received redirect_uri=%s", config.oauth_redirect_uri)
    try:
        refresh_token, channel_id, channel_title = await exchange_oauth_code(config, code, state)
        next_run = (
            utc_isoformat(
                calculate_next_run_at(config.update_frequency, config.schedule_time, config.timezone)
            )
            if config.schedule_enabled and config.update_frequency != "manual"
            else None
        )
        update_social_media_config(
            youtube_refresh_token=refresh_token,
            youtube_channel_id=channel_id,
            youtube_channel_title=channel_title,
            oauth_state=None,
            oauth_redirect_uri=None,
            next_run_at=next_run,
        )
    except Exception as exc:
        logger.exception("YouTube OAuth callback 失败: %s", exc)
        return RedirectResponse(f"{frontend}&youtube=error")
    logger.info(
        "social_media.oauth.callback.connected channel_id=%s channel_title=%s",
        channel_id,
        channel_title,
    )
    return RedirectResponse(f"{frontend}&youtube=connected")


@router.post("/youtube/disconnect", response_model=SocialMediaSettingsOut)
def disconnect_youtube_account() -> SocialMediaSettingsOut:
    current = load_social_media_config()
    disconnect_youtube()
    logger.info("social_media.oauth.disconnected channel_id=%s", current.youtube_channel_id)
    return _settings_out()


@router.post("/sync", response_model=SocialMediaRunOut, status_code=202)
def run_social_media_sync(session: Session = Depends(get_session)) -> SocialMediaRunOut:
    config = load_social_media_config()
    if not config.youtube_connected:
        raise HTTPException(status_code=400, detail="请先在 Social Media Settings 连接 YouTube")
    run = enqueue_social_media_run(session, "manual")
    logger.info(
        "social_media.sync.manual_requested run_id=%s status=%s channel_id=%s",
        run.id,
        run.status,
        config.youtube_channel_id,
    )
    return _run_out(run)


@router.get("/runs/latest", response_model=Optional[SocialMediaRunOut])
def latest_social_media_run(session: Session = Depends(get_session)) -> Optional[SocialMediaRunOut]:
    run = session.query(SocialMediaSyncRun).order_by(SocialMediaSyncRun.created_at.desc()).first()
    return _run_out(run) if run else None


@router.get("/videos", response_model=SocialMediaListOut)
def list_social_media_videos(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> SocialMediaListOut:
    config = load_social_media_config()
    query = (
        session.query(SocialMediaDataset)
        .filter(SocialMediaDataset.platform == "youtube")
        .filter(SocialMediaDataset.status == "complete")
    )
    if config.youtube_channel_id:
        query = query.filter(SocialMediaDataset.external_account_id == config.youtube_channel_id)
    dataset = query.order_by(
        SocialMediaDataset.metric_date.desc(),
        SocialMediaDataset.collected_at.desc(),
    ).first()
    if dataset is None:
        return SocialMediaListOut(metric_date=None, collected_at=None, total=0, items=[])
    snapshots = session.query(SocialMediaVideoSnapshot).filter(
        SocialMediaVideoSnapshot.dataset_id == dataset.id
    )
    total = snapshots.count()
    page = snapshots.order_by(SocialMediaVideoSnapshot.published_at.desc()).offset(offset).limit(limit).all()
    return SocialMediaListOut(
        metric_date=dataset.metric_date,
        collected_at=utc_isoformat(dataset.collected_at),
        total=total,
        items=[
            SocialMediaVideoOut(
                id=item.id,
                external_video_id=item.external_video_id,
                title=item.title,
                published_at=utc_isoformat(item.published_at),
                platform="YouTube",
                ctr=item.ctr,
                average_view_duration_seconds=item.average_view_duration_seconds,
                average_view_percentage=item.average_view_percentage,
                duration_seconds=item.duration_seconds,
                views=item.views,
                subscribers_gained=item.subscribers_gained,
                subscribers_lost=item.subscribers_lost,
                net_subscribers=item.net_subscribers,
            )
            for item in page
        ],
    )
