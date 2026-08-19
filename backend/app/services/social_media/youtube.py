"""YouTube OAuth、public 视频元数据和日级 Reporting 数据读取。"""
from __future__ import annotations

import csv
import io
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import SocialMediaConfig, update_social_media_config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
REPORTING_API = "https://youtubereporting.googleapis.com/v1"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)
BASIC_REPORT_TYPE = "channel_basic_a3"
REACH_REPORT_TYPE = "channel_reach_basic_a1"
REQUEST_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


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


def build_oauth_url(config: SocialMediaConfig, redirect_uri: str) -> str:
    if not config.youtube_client_id or not config.youtube_client_secret:
        raise ValueError("请先在 Social Media Settings 配置 YouTube OAuth Client ID 和 Client Secret")
    state = secrets.token_urlsafe(32)
    update_social_media_config(oauth_state=state, oauth_redirect_uri=redirect_uri)
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
    if not config.oauth_state or not secrets.compare_digest(config.oauth_state, state):
        raise ValueError("YouTube OAuth state 无效或已过期")
    if not config.youtube_client_id or not config.youtube_client_secret or not config.oauth_redirect_uri:
        raise ValueError("YouTube OAuth 配置不完整")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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
        token = response.json()
        refresh_token = token.get("refresh_token") or config.youtube_refresh_token
        access_token = token.get("access_token")
        if not refresh_token or not access_token:
            raise ValueError("Google 未返回 offline refresh token，请重新授权")
        channel_id, channel_title, _uploads = await _fetch_channel(client, access_token)
    return refresh_token, channel_id, channel_title


async def fetch_daily_dataset(config: SocialMediaConfig) -> YouTubeDailyDataset:
    access_token = await refresh_access_token(config)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        channel_id, channel_title, uploads_playlist_id = await _fetch_channel(client, access_token)
        videos = await _fetch_public_videos(client, access_token, uploads_playlist_id)
        basic_job_id, reach_job_id = await _ensure_reporting_jobs(client, access_token, config)
        basic_reports = await _list_reports(client, access_token, basic_job_id)
        reach_reports = await _list_reports(client, access_token, reach_job_id)
        metric_date, basic_report, reach_report = _latest_common_reports(basic_reports, reach_reports)
        basic_csv, reach_csv = await _download_reports(client, access_token, basic_report, reach_report)
    basic = _parse_basic_report(basic_csv, metric_date)
    reach = _parse_reach_report(reach_csv, metric_date)
    metrics_by_video: dict[str, DailyMetrics] = {}
    for video in videos:
        activity = basic.get(video.video_id)
        reach_metric = reach.get(video.video_id)
        metrics_by_video[video.video_id] = DailyMetrics(
            views=activity["views"] if activity else 0,
            ctr=reach_metric,
            average_view_duration_seconds=activity["avd"] if activity else None,
            average_view_percentage=activity["avp"] if activity else None,
            subscribers_gained=activity["gained"] if activity else 0,
            subscribers_lost=activity["lost"] if activity else 0,
        )
    return YouTubeDailyDataset(
        channel_id=channel_id,
        channel_title=channel_title,
        metric_date=metric_date,
        videos=videos,
        metrics_by_video=metrics_by_video,
    )


async def refresh_access_token(config: SocialMediaConfig) -> str:
    if not config.youtube_client_id or not config.youtube_client_secret or not config.youtube_refresh_token:
        raise ValueError("YouTube 尚未连接或 OAuth 配置不完整")
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": config.youtube_client_id,
                "client_secret": config.youtube_client_secret,
                "refresh_token": config.youtube_refresh_token,
                "grant_type": "refresh_token",
            },
        )
    _raise_google_error(response)
    token = response.json().get("access_token")
    if not token:
        raise ValueError("Google access token 刷新失败")
    return str(token)


async def _fetch_channel(client: httpx.AsyncClient, token: str) -> tuple[str, str, str]:
    response = await client.get(
        f"{YOUTUBE_API}/channels",
        params={"part": "snippet,contentDetails", "mine": "true"},
        headers=_auth_headers(token),
    )
    _raise_google_error(response)
    items = response.json().get("items") or []
    if not items:
        raise ValueError("当前 Google 账号没有可访问的 YouTube 频道")
    channel = items[0]
    return (
        str(channel["id"]),
        str(channel.get("snippet", {}).get("title") or channel["id"]),
        str(channel["contentDetails"]["relatedPlaylists"]["uploads"]),
    )


async def _fetch_public_videos(
    client: httpx.AsyncClient,
    token: str,
    uploads_playlist_id: str,
) -> list[YouTubeVideo]:
    ids: list[str] = []
    page_token: str | None = None
    while True:
        params = {"part": "contentDetails", "playlistId": uploads_playlist_id, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        response = await client.get(
            f"{YOUTUBE_API}/playlistItems",
            params=params,
            headers=_auth_headers(token),
        )
        _raise_google_error(response)
        body = response.json()
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
        response = await client.get(
            f"{YOUTUBE_API}/videos",
            params={"part": "snippet,contentDetails,status", "id": ",".join(ids[index : index + 50])},
            headers=_auth_headers(token),
        )
        _raise_google_error(response)
        for item in response.json().get("items") or []:
            if item.get("status", {}).get("privacyStatus") != "public":
                continue
            snippet = item.get("snippet", {})
            videos.append(
                YouTubeVideo(
                    video_id=str(item["id"]),
                    title=str(snippet.get("title") or item["id"]),
                    published_at=_parse_google_datetime(str(snippet["publishedAt"])),
                    duration_seconds=_parse_duration(str(item.get("contentDetails", {}).get("duration") or "PT0S")),
                )
            )
    return sorted(videos, key=lambda video: video.published_at, reverse=True)


async def _ensure_reporting_jobs(
    client: httpx.AsyncClient,
    token: str,
    config: SocialMediaConfig,
) -> tuple[str, str]:
    response = await client.get(f"{REPORTING_API}/jobs", headers=_auth_headers(token))
    _raise_google_error(response)
    by_type = {str(job.get("reportTypeId")): str(job["id"]) for job in response.json().get("jobs") or []}
    basic_id = config.youtube_basic_job_id or by_type.get(BASIC_REPORT_TYPE)
    reach_id = config.youtube_reach_job_id or by_type.get(REACH_REPORT_TYPE)
    if not basic_id:
        basic_id = await _create_job(client, token, BASIC_REPORT_TYPE, "Sparkling daily activity")
    if not reach_id:
        reach_id = await _create_job(client, token, REACH_REPORT_TYPE, "Sparkling daily reach")
    if basic_id != config.youtube_basic_job_id or reach_id != config.youtube_reach_job_id:
        update_social_media_config(youtube_basic_job_id=basic_id, youtube_reach_job_id=reach_id)
    return basic_id, reach_id


async def _create_job(client: httpx.AsyncClient, token: str, report_type: str, name: str) -> str:
    response = await client.post(
        f"{REPORTING_API}/jobs",
        json={"reportTypeId": report_type, "name": name},
        headers=_auth_headers(token),
    )
    _raise_google_error(response)
    return str(response.json()["id"])


async def _list_reports(client: httpx.AsyncClient, token: str, job_id: str) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params: dict[str, object] = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token
        response = await client.get(
            f"{REPORTING_API}/jobs/{job_id}/reports",
            params=params,
            headers=_auth_headers(token),
        )
        _raise_google_error(response)
        body = response.json()
        reports.extend(body.get("reports") or [])
        page_token = body.get("nextPageToken")
        if not page_token:
            return reports


def _latest_common_reports(
    basic_reports: list[dict[str, Any]],
    reach_reports: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    def latest_by_date(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for report in reports:
            metric_date = str(report.get("startTime") or "")[:10]
            if not metric_date:
                continue
            current = result.get(metric_date)
            if current is None or str(report.get("createTime") or "") > str(current.get("createTime") or ""):
                result[metric_date] = report
        return result

    basic = latest_by_date(basic_reports)
    reach = latest_by_date(reach_reports)
    common = sorted(set(basic) & set(reach))
    if not common:
        raise ValueError("YouTube 日报尚未生成完整的 activity + reach 数据，请稍后再同步")
    metric_date = common[-1]
    return metric_date, basic[metric_date], reach[metric_date]


async def _download_reports(
    client: httpx.AsyncClient,
    token: str,
    basic_report: dict[str, Any],
    reach_report: dict[str, Any],
) -> tuple[str, str]:
    async def download(report: dict[str, Any]) -> str:
        url = report.get("downloadUrl")
        if not url:
            raise ValueError("YouTube report 缺少 downloadUrl")
        response = await client.get(str(url), headers=_auth_headers(token))
        _raise_google_error(response)
        return response.text

    return await download(basic_report), await download(reach_report)


def _parse_basic_report(raw: str, metric_date: str) -> dict[str, dict[str, float | int | None]]:
    totals: dict[str, dict[str, float]] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("date") != metric_date or not row.get("video_id"):
            continue
        video_id = str(row["video_id"])
        entry = totals.setdefault(
            video_id,
            {"views": 0.0, "watch_seconds": 0.0, "avp_weighted": 0.0, "avp_views": 0.0, "gained": 0.0, "lost": 0.0},
        )
        views = _float(row.get("views"))
        entry["views"] += views
        entry["watch_seconds"] += _float(row.get("watch_time_minutes")) * 60
        if row.get("average_view_duration_percentage") not in {None, ""} and views > 0:
            entry["avp_weighted"] += _float(row.get("average_view_duration_percentage")) * views
            entry["avp_views"] += views
        entry["gained"] += _float(row.get("subscribers_gained"))
        entry["lost"] += _float(row.get("subscribers_lost"))
    result: dict[str, dict[str, float | int | None]] = {}
    for video_id, entry in totals.items():
        views = int(entry["views"])
        result[video_id] = {
            "views": views,
            "avd": entry["watch_seconds"] / entry["views"] if entry["views"] else None,
            "avp": entry["avp_weighted"] / entry["avp_views"] if entry["avp_views"] else None,
            "gained": int(entry["gained"]),
            "lost": int(entry["lost"]),
        }
    return result


def _parse_reach_report(raw: str, metric_date: str) -> dict[str, float | None]:
    totals: dict[str, tuple[float, float]] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        if row.get("date") != metric_date or not row.get("video_id"):
            continue
        video_id = str(row["video_id"])
        impressions = _float(row.get("video_thumbnail_impressions"))
        ctr = _float(row.get("video_thumbnail_impressions_ctr"))
        weighted, total_impressions = totals.get(video_id, (0.0, 0.0))
        totals[video_id] = (weighted + ctr * impressions, total_impressions + impressions)
    return {
        video_id: weighted / impressions if impressions else None
        for video_id, (weighted, impressions) in totals.items()
    }


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _raise_google_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        body = response.json()
        detail = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("error")
    except ValueError:
        detail = response.text
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


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
