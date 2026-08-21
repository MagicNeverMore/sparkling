"""对当前已连接 YouTube 频道发起只读探测，并保存脱敏后的原始 API JSON。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.services.social_media.config import load_social_media_config
from app.services.social_media.youtube import ANALYTICS_TIMEZONE, _refresh_credentials


def _execute(request: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "body": request.execute()}
    except HttpError as exc:
        return {
            "ok": False,
            "error": {
                "kind": "HttpError",
                "status": getattr(exc.resp, "status", None),
                "content": exc.content.decode("utf-8", errors="replace"),
            },
        }
    except Exception as exc:
        return {"ok": False, "error": {"kind": type(exc).__name__, "message": str(exc)}}


def _metric_date(value: str | None) -> str:
    if value:
        return value
    return (datetime.now(ANALYTICS_TIMEZONE).date() - timedelta(days=1)).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric-date", help="YYYY-MM-DD；默认前一个完整太平洋日")
    parser.add_argument("--output-dir", default="test-output")
    args = parser.parse_args()

    config = load_social_media_config()
    if not config.youtube_connected:
        raise SystemExit("YouTube 尚未连接，无法发起真实 API 探测")
    metric_date = _metric_date(args.metric_date)
    credentials = _refresh_credentials(config)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)
    reporting = build("youtubereporting", "v1", credentials=credentials, cache_discovery=False)

    channel = _execute(youtube.channels().list(part="snippet,contentDetails", mine=True))
    uploads_playlist_id: str | None = None
    if channel["ok"]:
        items = channel["body"].get("items") or []
        if items:
            uploads_playlist_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

    playlist = (
        _execute(youtube.playlistItems().list(part="contentDetails", playlistId=uploads_playlist_id, maxResults=50))
        if uploads_playlist_id
        else {"ok": False, "error": {"kind": "MissingUploadsPlaylist"}}
    )
    video_ids = [
        item.get("contentDetails", {}).get("videoId")
        for item in (playlist.get("body", {}).get("items") or [])
        if item.get("contentDetails", {}).get("videoId")
    ]
    videos = (
        _execute(youtube.videos().list(part="snippet,contentDetails,status,statistics", id=",".join(video_ids)))
        if video_ids
        else {"ok": True, "body": {"items": []}}
    )
    public_video_ids = [
        item["id"]
        for item in (videos.get("body", {}).get("items") or [])
        if item.get("status", {}).get("privacyStatus") == "public"
    ]
    metrics = "views,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
    analytics_query = _execute(
        analytics.reports().query(
            ids="channel==MINE",
            startDate=metric_date,
            endDate=metric_date,
            metrics=metrics,
            dimensions="video",
            filters=f"video=={','.join(public_video_ids)}",
            maxResults=200,
        )
    )
    reporting_jobs = _execute(reporting.jobs().list())
    reach_job_id = next(
        (
            job.get("id")
            for job in (reporting_jobs.get("body", {}).get("jobs") or [])
            if job.get("reportTypeId") == "channel_reach_basic_a1"
        ),
        None,
    )
    reporting_reach_reports = (
        _execute(reporting.jobs().reports().list(jobId=reach_job_id))
        if reach_job_id
        else {"ok": False, "error": {"kind": "MissingReachJob"}}
    )

    probe = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": {
            "metric_date": metric_date,
            "analytics": {
                "ids": "channel==MINE",
                "startDate": metric_date,
                "endDate": metric_date,
                "dimensions": "video",
                "filters": f"video=={','.join(public_video_ids)}",
                "metrics": metrics,
            },
        },
        "responses": {
            "channels_list": channel,
            "playlist_items_list": playlist,
            "videos_list": videos,
            "analytics_reports_query": analytics_query,
            "reporting_jobs_list": reporting_jobs,
            "reporting_reach_reports_list": reporting_reach_reports,
        },
        "note": "不含 access token、refresh token、OAuth client secret 或 Authorization header。",
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"youtube-api-probe-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())


if __name__ == "__main__":
    main()
