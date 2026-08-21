"""YouTube Web OAuth 与官方 Python SDK 的 Analytics 小时快照读取。"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import anyio
import httpx
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ...logger import get_logger
from .config import SocialMediaConfig, update_social_media_config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
ANALYTICS_TIMEZONE = ZoneInfo("America/Los_Angeles")
ANALYTICS_VIDEO_BATCH_SIZE = 200
ANALYTICS_LOOKBACK_DAYS = 10
REPORTING_REACH_REPORT_TYPE = "channel_reach_basic_a1"
REPORTING_MAX_CANDIDATES = 7

logger = get_logger(__name__)


def oauth_trace_id(state: str | None) -> str:
    """用不可逆短摘要关联 OAuth 日志，不记录原始 state。"""
    if not state:
        return "missing"
    return hashlib.sha256(state.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    title: str
    published_at: datetime
    duration_seconds: int


@dataclass(frozen=True)
class DailyMetrics:
    views: int
    ctr: float | None
    average_view_duration_seconds: float | None
    average_view_percentage: float | None
    subscribers_gained: int
    subscribers_lost: int


@dataclass(frozen=True)
class YouTubeDailyDataset:
    channel_id: str
    channel_title: str
    metric_date: str
    videos: list[YouTubeVideo]
    metrics_by_video: dict[str, DailyMetrics]
    metrics_by_date: dict[str, dict[str, DailyMetrics]] | None = None

    def daily_metrics(self) -> dict[str, dict[str, DailyMetrics]]:
        """兼容旧调用方；新采集一次返回最近十天所有有数据日期。"""
        return self.metrics_by_date if self.metrics_by_date is not None else {
            self.metric_date: self.metrics_by_video
        }


def build_oauth_url(config: SocialMediaConfig, redirect_uri: str) -> str:
    if not config.youtube_client_id or not config.youtube_client_secret:
        raise ValueError("请先在 Social Media Settings 配置 YouTube OAuth Client ID 和 Client Secret")
    state = secrets.token_urlsafe(32)
    update_social_media_config(oauth_state=state, oauth_redirect_uri=redirect_uri)
    logger.info(
        "youtube.oauth.start trace_id=%s redirect_uri=%s scopes=%s",
        oauth_trace_id(state),
        redirect_uri,
        len(SCOPES),
    )
    query = urlencode(
        {
            "client_id": config.youtube_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


async def exchange_oauth_code(config: SocialMediaConfig, code: str, state: str) -> tuple[str, str, str]:
    trace_id = oauth_trace_id(state)
    state_matches = bool(
        config.oauth_state and secrets.compare_digest(config.oauth_state, state)
    )
    logger.info(
        "youtube.oauth.exchange.start trace_id=%s stored_trace_id=%s state_match=%s "
        "redirect_uri=%s client_configured=%s",
        trace_id,
        oauth_trace_id(config.oauth_state),
        state_matches,
        config.oauth_redirect_uri,
        bool(config.youtube_client_id and config.youtube_client_secret),
    )
    if not state_matches:
        raise ValueError("YouTube OAuth state 无效或已过期")
    if not config.youtube_client_id or not config.youtube_client_secret or not config.oauth_redirect_uri:
        raise ValueError("YouTube OAuth 配置不完整")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        logger.info(
            "youtube.oauth.token_request.start trace_id=%s redirect_uri=%s",
            trace_id,
            config.oauth_redirect_uri,
        )
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": config.youtube_client_id,
                "client_secret": config.youtube_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config.oauth_redirect_uri,
            },
        )
        _raise_google_error(response)
        logger.info(
            "youtube.oauth.token_request.done trace_id=%s status=%s",
            trace_id,
            response.status_code,
        )
        token = response.json()
        returned_refresh_token = token.get("refresh_token")
        refresh_token = returned_refresh_token or config.youtube_refresh_token
        access_token = token.get("access_token")
        logger.info(
            "youtube.oauth.token.received trace_id=%s status=%s access_credential_present=%s "
            "refresh_credential_present=%s refresh_credential_source=%s",
            trace_id,
            response.status_code,
            bool(access_token),
            bool(refresh_token),
            "google" if returned_refresh_token else "stored",
        )
        if not refresh_token or not access_token:
            raise ValueError("Google 未返回 offline refresh token，请重新授权")
        channel_id, channel_title, _uploads = await anyio.to_thread.run_sync(
            _fetch_oauth_channel_with_sdk,
            access_token,
        )
    logger.info(
        "youtube.oauth.exchange.done trace_id=%s channel_id=%s channel_title=%s",
        trace_id,
        channel_id,
        channel_title,
    )
    return refresh_token, channel_id, channel_title


async def fetch_daily_dataset(config: SocialMediaConfig) -> YouTubeDailyDataset:
    """异步 worker 入口；SDK 调用在线程中执行，避免阻塞事件循环。"""
    # Google SDK/httplib2 是同步 I/O。超时时必须让 worker 协程继续进入失败收尾，
    # 不可等待卡死的线程，否则 run 会永久保持 running。线程即使晚些返回也只会产出
    # 内存中的 dataset，collector 会拒绝发布已终结 run 的结果。
    return await anyio.to_thread.run_sync(_fetch_analytics_dataset, config, abandon_on_cancel=True)


def _fetch_analytics_dataset(config: SocialMediaConfig) -> YouTubeDailyDataset:
    """Analytics adapter 的深模块接口：凭据刷新、官方 SDK 查询、public 视频合并。"""
    logger.info("youtube.analytics.dataset.start channel_id=%s", config.youtube_channel_id)
    credentials = _refresh_credentials(config)
    youtube_client = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    analytics_client = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)
    reporting_client = build("youtubereporting", "v1", credentials=credentials, cache_discovery=False)
    channel_id, channel_title, uploads_playlist_id = _fetch_channel_sdk(youtube_client)
    videos = _fetch_public_videos_sdk(youtube_client, uploads_playlist_id)
    # Analytics 指标存在处理延迟。扫描最近十个太平洋日，再使用最新实际有
    # 视频行的日期，避免固定查询昨天时把未处理完成的数据误记为 0/空。
    end_date = datetime.now(ANALYTICS_TIMEZONE).date()
    start_date = end_date - timedelta(days=ANALYTICS_LOOKBACK_DAYS - 1)
    activity_by_date = _fetch_video_metrics_sdk(
        analytics_client,
        start_date.isoformat(),
        end_date.isoformat(),
        videos,
    )
    metric_date, activity = _select_latest_activity_date(activity_by_date, end_date.isoformat())
    reach = _fetch_reach_metrics_from_reporting_sdk(
        reporting_client,
        credentials,
        metric_date,
    )
    metrics_by_date = {
        data_date: {
            video.video_id: _daily_metrics(
                rows.get(video.video_id, {}),
                reach if data_date == metric_date else {},
                video.video_id,
            )
            for video in videos
        }
        for data_date, rows in activity_by_date.items()
        if rows
    }
    metrics_by_video = metrics_by_date.get(metric_date, {})
    activity_matches = sum(video.video_id in activity for video in videos)
    reach_matches = sum(video.video_id in reach for video in videos)
    logger.info(
        "youtube.analytics.dataset.ready channel_id=%s metric_date=%s public_videos=%s "
        "activity_matches=%s reach_matches=%s data_dates=%s",
        channel_id,
        metric_date,
        len(videos),
        activity_matches,
        reach_matches,
        len(metrics_by_date),
    )
    return YouTubeDailyDataset(
        channel_id=channel_id,
        channel_title=channel_title,
        metric_date=metric_date,
        videos=videos,
        metrics_by_video=metrics_by_video,
        metrics_by_date=metrics_by_date,
    )


def _daily_metrics(
    activity: dict[str, Any],
    reach: dict[str, dict[str, Any]],
    video_id: str,
) -> DailyMetrics:
    return DailyMetrics(
        views=_int_metric(activity.get("views")),
        ctr=_optional_float(reach.get(video_id, {}).get("videoThumbnailImpressionsClickRate")),
        average_view_duration_seconds=_optional_float(activity.get("averageViewDuration")),
        average_view_percentage=_optional_float(activity.get("averageViewPercentage")),
        subscribers_gained=_int_metric(activity.get("subscribersGained")),
        subscribers_lost=_int_metric(activity.get("subscribersLost")),
    )


def _refresh_credentials(config: SocialMediaConfig) -> Credentials:
    if not config.youtube_client_id or not config.youtube_client_secret or not config.youtube_refresh_token:
        raise ValueError("YouTube 尚未连接或 OAuth 配置不完整")
    credentials = Credentials(
        token=None,
        refresh_token=config.youtube_refresh_token,
        token_uri=TOKEN_URL,
        client_id=config.youtube_client_id,
        client_secret=config.youtube_client_secret,
        scopes=SCOPES,
    )
    logger.info(
        "youtube.credentials.refresh.start channel_id=%s refresh_credential_present=%s",
        config.youtube_channel_id,
        bool(config.youtube_refresh_token),
    )
    try:
        credentials.refresh(GoogleRequest())
    except RefreshError as exc:
        logger.exception("youtube.credentials.refresh.failed channel_id=%s error=%s", config.youtube_channel_id, exc)
        raise ValueError("YouTube credential 刷新失败，请重新连接账号") from exc
    except Exception:
        logger.exception("youtube.credentials.refresh.failed channel_id=%s", config.youtube_channel_id)
        raise
    logger.info(
        "youtube.credentials.refresh.done channel_id=%s access_credential_present=%s expiry=%s",
        config.youtube_channel_id,
        bool(credentials.token),
        credentials.expiry,
    )
    return credentials


def _fetch_channel_sdk(youtube_client: Any) -> tuple[str, str, str]:
    body = _execute_google_request(
        youtube_client.channels().list(part="snippet,contentDetails", mine=True),
        service="youtube",
        operation="channels.list",
    )
    items = body.get("items") or []
    if not items:
        raise ValueError("当前 Google 账号没有可访问的 YouTube 频道")
    channel = items[0]
    result = (
        str(channel["id"]),
        str(channel.get("snippet", {}).get("title") or channel["id"]),
        str(channel["contentDetails"]["relatedPlaylists"]["uploads"]),
    )
    logger.info("youtube.api.channel.ready channel_id=%s channel_title=%s", result[0], result[1])
    return result


def _fetch_public_videos_sdk(youtube_client: Any, uploads_playlist_id: str) -> list[YouTubeVideo]:
    ids: list[str] = []
    page_token: str | None = None
    while True:
        request = youtube_client.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            **({"pageToken": page_token} if page_token else {}),
        )
        body = _execute_google_request(request, service="youtube", operation="playlistItems.list")
        ids.extend(
            str(item.get("contentDetails", {}).get("videoId"))
            for item in body.get("items") or []
            if item.get("contentDetails", {}).get("videoId")
        )
        page_token = body.get("nextPageToken")
        if not page_token:
            break

    videos: list[YouTubeVideo] = []
    for index in range(0, len(ids), 50):
        body = _execute_google_request(
            youtube_client.videos().list(
                part="snippet,contentDetails,status",
                id=",".join(ids[index : index + 50]),
            ),
            service="youtube",
            operation="videos.list",
        )
        for item in body.get("items") or []:
            if item.get("status", {}).get("privacyStatus") != "public":
                continue
            snippet = item.get("snippet", {})
            videos.append(
                YouTubeVideo(
                    video_id=str(item["id"]),
                    title=str(snippet.get("title") or item["id"]),
                    published_at=_parse_google_datetime(str(snippet["publishedAt"])),
                    duration_seconds=_parse_duration(
                        str(item.get("contentDetails", {}).get("duration") or "PT0S")
                    ),
                )
            )
    result = sorted(videos, key=lambda video: video.published_at, reverse=True)
    logger.info("youtube.api.public_videos.ready upload_items=%s public_videos=%s", len(ids), len(result))
    return result


def _fetch_video_metrics_sdk(
    analytics_client: Any,
    start_date: str,
    end_date: str,
    videos: list[YouTubeVideo],
) -> dict[str, dict[str, dict[str, Any]]]:
    activity_by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for index in range(0, len(videos), ANALYTICS_VIDEO_BATCH_SIZE):
        video_ids = [video.video_id for video in videos[index : index + ANALYTICS_VIDEO_BATCH_SIZE]]
        if not video_ids:
            continue
        common = {
            "ids": "channel==MINE",
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": "day,video",
            "filters": f"video=={','.join(video_ids)}",
            "maxResults": ANALYTICS_VIDEO_BATCH_SIZE * ANALYTICS_LOOKBACK_DAYS,
        }
        rows = _query_analytics_rows_by_day(
            analytics_client,
            start_date,
            end_date,
            "views,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost",
            common,
        )
        for day, metrics_by_video in rows.items():
            activity_by_date.setdefault(day, {}).update(metrics_by_video)
    logger.info(
        "youtube.analytics.metrics.ready start_date=%s end_date=%s dates=%s activity_rows=%s",
        start_date,
        end_date,
        len(activity_by_date),
        sum(len(rows) for rows in activity_by_date.values()),
    )
    return activity_by_date


def _select_latest_activity_date(
    activity_by_date: dict[str, dict[str, dict[str, Any]]],
    fallback_date: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    available_dates = [day for day, rows in activity_by_date.items() if rows]
    if not available_dates:
        logger.warning(
            "youtube.analytics.latest_date_unavailable fallback_date=%s",
            fallback_date,
        )
        return fallback_date, {}
    metric_date = max(available_dates)
    activity = activity_by_date[metric_date]
    logger.info(
        "youtube.analytics.latest_date_selected metric_date=%s videos=%s",
        metric_date,
        len(activity),
    )
    return metric_date, activity


def _query_analytics_rows_by_day(
    analytics_client: Any,
    start_date: str,
    end_date: str,
    metrics: str,
    params: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    logger.info(
        "youtube.analytics.query.start start_date=%s end_date=%s metrics=%s video_count=%s",
        start_date,
        end_date,
        metrics,
        len(str(params["filters"]).removeprefix("video==").split(",")),
    )
    body = _execute_google_request(
        analytics_client.reports().query(metrics=metrics, **params),
        service="youtubeAnalytics",
        operation="reports.query",
    )
    headers = [str(column.get("name")) for column in body.get("columnHeaders") or []]
    day_index = headers.index("day") if "day" in headers else None
    video_index = headers.index("video") if "video" in headers else None
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for values in body.get("rows") or []:
        if day_index is None or video_index is None or not values:
            continue
        day, video_id = values[day_index], values[video_index]
        if day and video_id:
            result.setdefault(str(day), {})[str(video_id)] = dict(zip(headers, values, strict=False))
    logger.info(
        "youtube.analytics.query.done start_date=%s end_date=%s metrics=%s dates=%s rows=%s columns=%s",
        start_date,
        end_date,
        metrics,
        len(result),
        sum(len(rows) for rows in result.values()),
        headers,
    )
    return result


def _fetch_reach_metrics_from_reporting_sdk(
    reporting_client: Any,
    credentials: Credentials,
    metric_date: str,
) -> dict[str, dict[str, Any]]:
    """从官方 Reporting API 下载已生成的 Reach CSV，并只返回目标日期的视频 CTR。

    Reporting API 的 Job/Report 元数据是 JSON；Google 规定下载的报表正文为 CSV。
    CSV 仅在内存中解析，绝不作为应用文件留存。报表尚未生成属于正常延迟，不影响
    同一轮中其他 Analytics API 指标的入库。
    """
    job_id = _get_or_create_reach_reporting_job(reporting_client)
    reports = _list_reporting_reports(reporting_client, job_id)
    candidates = [
        report for report in reports
        if _report_may_include_date(report, metric_date)
    ][:REPORTING_MAX_CANDIDATES]
    if not candidates:
        logger.info(
            "youtube.reporting.reach_not_ready job_id=%s metric_date=%s available_reports=%s",
            job_id,
            metric_date,
            len(reports),
        )
        return {}

    for report in candidates:
        report_id = str(report.get("id") or "unknown")
        download_url = report.get("downloadUrl")
        if not isinstance(download_url, str) or not download_url:
            logger.warning(
                "youtube.reporting.reach_report_missing_download_url job_id=%s report_id=%s",
                job_id,
                report_id,
            )
            continue
        payload = _download_reporting_csv(credentials, download_url, job_id, report_id)
        rows = _parse_reach_report_csv(payload, metric_date)
        if rows:
            logger.info(
                "youtube.reporting.reach.ready job_id=%s report_id=%s metric_date=%s video_rows=%s",
                job_id,
                report_id,
                metric_date,
                len(rows),
            )
            return rows

    logger.info(
        "youtube.reporting.reach_not_ready job_id=%s metric_date=%s reason=no_matching_rows",
        job_id,
        metric_date,
    )
    return {}


def _get_or_create_reach_reporting_job(reporting_client: Any) -> str:
    body = _execute_google_request(
        reporting_client.jobs().list(),
        service="youtubeReporting",
        operation="jobs.list",
    )
    for job in body.get("jobs") or []:
        if job.get("reportTypeId") == REPORTING_REACH_REPORT_TYPE and job.get("id"):
            job_id = str(job["id"])
            logger.info("youtube.reporting.reach_job.reused job_id=%s", job_id)
            return job_id

    body = _execute_google_request(
        reporting_client.jobs().create(
            body={
                "reportTypeId": REPORTING_REACH_REPORT_TYPE,
                "name": "Sparkling video CTR reach report",
            }
        ),
        service="youtubeReporting",
        operation="jobs.create",
    )
    job_id = body.get("id")
    if not job_id:
        raise ValueError("YouTube Reporting API 未返回 Reach Report Job ID")
    logger.info("youtube.reporting.reach_job.created job_id=%s", job_id)
    return str(job_id)


def _list_reporting_reports(reporting_client: Any, job_id: str) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        body = _execute_google_request(
            reporting_client.jobs().reports().list(
                jobId=job_id,
                **({"pageToken": page_token} if page_token else {}),
            ),
            service="youtubeReporting",
            operation="jobs.reports.list",
        )
        reports.extend(report for report in body.get("reports") or [] if isinstance(report, dict))
        page_token = body.get("nextPageToken")
        if not page_token:
            break
    return sorted(reports, key=lambda report: str(report.get("startTime") or ""), reverse=True)


def _report_may_include_date(report: dict[str, Any], metric_date: str) -> bool:
    start = str(report.get("startTime") or "")[:10]
    end = str(report.get("endTime") or "")[:10]
    return bool(start and end and start <= metric_date <= end)


def _download_reporting_csv(
    credentials: Credentials,
    download_url: str,
    job_id: str,
    report_id: str,
) -> bytes:
    logger.info(
        "youtube.reporting.download.start job_id=%s report_id=%s",
        job_id,
        report_id,
    )
    try:
        response, payload = AuthorizedHttp(credentials).request(download_url, method="GET")
        status = int(getattr(response, "status", 0))
        if not 200 <= status < 300:
            raise ValueError(f"HTTP {status}")
    except Exception as exc:
        logger.exception(
            "youtube.reporting.download.failed job_id=%s report_id=%s error=%s",
            job_id,
            report_id,
            exc,
        )
        raise ValueError("YouTube Reach Report 下载失败") from exc
    logger.info(
        "youtube.reporting.download.done job_id=%s report_id=%s bytes=%s",
        job_id,
        report_id,
        len(payload),
    )
    return bytes(payload)


def _parse_reach_report_csv(payload: bytes, metric_date: str) -> dict[str, dict[str, Any]]:
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    result: dict[str, dict[str, Any]] = {}
    for row in reader:
        if row.get("date") != metric_date or not row.get("video_id"):
            continue
        result[str(row["video_id"])] = {
            "videoThumbnailImpressions": row.get("video_thumbnail_impressions"),
            "videoThumbnailImpressionsClickRate": row.get("video_thumbnail_impressions_ctr"),
        }
    logger.info(
        "youtube.reporting.parse.done metric_date=%s video_rows=%s",
        metric_date,
        len(result),
    )
    return result


def _execute_google_request(request: Any, *, service: str, operation: str) -> dict[str, Any]:
    logger.info("youtube.api.request.start service=%s operation=%s", service, operation)
    try:
        body = request.execute()
    except HttpError as exc:
        status = getattr(exc.resp, "status", "unknown")
        logger.exception("youtube.api.request.failed service=%s operation=%s status=%s", service, operation, status)
        raise ValueError(f"YouTube {service} {operation} 请求失败 ({status})") from exc
    except Exception:
        logger.exception("youtube.api.request.failed service=%s operation=%s", service, operation)
        raise
    logger.info("youtube.api.request.done service=%s operation=%s", service, operation)
    return body


def _int_metric(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_oauth_channel_with_sdk(access_token: str) -> tuple[str, str, str]:
    """OAuth code 兑换完成后，用官方 SDK 验证获授权频道。"""
    logger.info("youtube.oauth.channel_request.start")
    credentials = Credentials(token=access_token, scopes=SCOPES)
    client = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    result = _fetch_channel_sdk(client)
    logger.info("youtube.oauth.channel_request.done channel_id=%s", result[0])
    return result


def _raise_google_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    error_code = None
    error_reason = None
    try:
        body = response.json()
        error = body.get("error")
        if isinstance(error, dict):
            detail = error.get("message")
            error_code = error.get("status") or error.get("code")
            errors = error.get("errors") or []
            if errors and isinstance(errors[0], dict):
                error_reason = errors[0].get("reason")
        else:
            detail = error
    except ValueError:
        detail = response.text
    try:
        request_method = response.request.method
        request_path = response.request.url.path
    except RuntimeError:
        request_method = "UNKNOWN"
        request_path = "unknown"
    logger.error(
        "youtube.google_api.error method=%s path=%s status=%s error_code=%s reason=%s detail=%s",
        request_method,
        request_path,
        response.status_code,
        error_code,
        error_reason,
        detail or response.reason_phrase,
    )
    raise ValueError(f"YouTube request failed ({response.status_code}): {detail or response.reason_phrase}")


def _parse_google_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_duration(value: str) -> int:
    match = re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        return 0
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
