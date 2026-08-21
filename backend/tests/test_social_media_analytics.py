from __future__ import annotations

import os
import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, Request

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-social-media-analytics-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(
    tempfile.gettempdir(),
    "sparkling-social-media-analytics-control.db",
)
os.environ["SPARKLING_DB_PATH"] = _TEST_DB_PATH
os.environ["SPARKLING_CONTROL_DB_PATH"] = _TEST_CONTROL_DB_PATH
Path(_TEST_DB_PATH).touch(exist_ok=True)


def _youtube_module() -> ModuleType:
    from app.services.social_media import youtube

    return youtube


class SocialMediaAnalyticsTest(unittest.TestCase):
    def test_analytics_sdk_rows_map_activity_metrics_to_video(self) -> None:
        youtube = _youtube_module()

        class Request:
            def __init__(self, body: dict) -> None:
                self.body = body

            def execute(self) -> dict:
                return self.body

        class Reports:
            def query(self, *, metrics: str, **_params: object) -> Request:
                if metrics.startswith("views,"):
                    return Request(
                        {
                            "columnHeaders": [
                                {"name": "day"},
                                {"name": "video"},
                                {"name": "views"},
                                {"name": "averageViewDuration"},
                                {"name": "averageViewPercentage"},
                                {"name": "subscribersGained"},
                                {"name": "subscribersLost"},
                            ],
                            "rows": [["2026-08-18", "video-1", 42, 63.5, 51.2, 3, 1]],
                        }
                    )
                raise AssertionError("CTR targeted query must not be sent")

        class AnalyticsClient:
            def reports(self) -> Reports:
                return Reports()

        videos = [
            youtube.YouTubeVideo(
                video_id="video-1",
                title="Video",
                published_at=datetime(2026, 8, 20),
                duration_seconds=120,
            )
        ]
        activity_by_date = youtube._fetch_video_metrics_sdk(
            AnalyticsClient(),
            "2026-08-11",
            "2026-08-20",
            videos,
        )
        metric_date, activity = youtube._select_latest_activity_date(
            activity_by_date,
            "2026-08-20",
        )

        self.assertEqual(metric_date, "2026-08-18")
        self.assertEqual(activity["video-1"]["views"], 42)
        self.assertEqual(activity["video-1"]["averageViewDuration"], 63.5)
        self.assertEqual(activity["video-1"]["subscribersGained"], 3)

    def test_latest_activity_date_uses_most_recent_nonempty_day(self) -> None:
        youtube = _youtube_module()
        metric_date, activity = youtube._select_latest_activity_date(
            {
                "2026-08-16": {"old-video": {"views": 5}},
                "2026-08-18": {"new-video": {"views": 8}},
                "2026-08-19": {},
            },
            "2026-08-20",
        )

        self.assertEqual(metric_date, "2026-08-18")
        self.assertEqual(activity, {"new-video": {"views": 8}})

    def test_reach_report_csv_maps_ctr_only_for_requested_date(self) -> None:
        youtube = _youtube_module()
        payload = (
            b"date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
            b"2026-08-19,video-1,1200,5.25\n"
            b"2026-08-18,video-2,800,3.5\n"
        )

        reach = youtube._parse_reach_report_csv(payload, "2026-08-19")

        self.assertEqual(reach, {
            "video-1": {
                "videoThumbnailImpressions": "1200",
                "videoThumbnailImpressionsClickRate": "5.25",
            }
        })

    def test_reach_job_is_created_then_csv_is_downloaded_from_reporting_api(self) -> None:
        youtube = _youtube_module()

        class Request:
            def __init__(self, body: dict) -> None:
                self.body = body

            def execute(self) -> dict:
                return self.body

        class Reports:
            def list(self, **_params: object) -> Request:
                return Request({
                    "reports": [{
                        "id": "report-1",
                        "startTime": "2026-08-19T00:00:00Z",
                        "endTime": "2026-08-19T23:59:59Z",
                        "downloadUrl": "https://reports.example/report-1",
                    }]
                })

        class Jobs:
            def list(self) -> Request:
                return Request({"jobs": []})

            def create(self, *, body: dict) -> Request:
                self.created_body = body
                return Request({"id": "job-1"})

            def reports(self) -> Reports:
                return Reports()

        class ReportingClient:
            def __init__(self) -> None:
                self.jobs_client = Jobs()

            def jobs(self) -> Jobs:
                return self.jobs_client

        class Response:
            status = 200

        client = ReportingClient()
        with patch.object(
            youtube,
            "AuthorizedHttp",
            return_value=SimpleNamespace(request=lambda *_args, **_kwargs: (Response(), (
                b"date,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
                b"2026-08-19,video-1,1200,5.25\n"
            ))),
        ):
            reach = youtube._fetch_reach_metrics_from_reporting_sdk(
                client,
                SimpleNamespace(),
                "2026-08-19",
            )

        self.assertEqual(client.jobs_client.created_body["reportTypeId"], "channel_reach_basic_a1")
        self.assertEqual(reach["video-1"]["videoThumbnailImpressionsClickRate"], "5.25")

    def test_fetch_daily_dataset_uses_analytics_adapter(self) -> None:
        youtube = _youtube_module()
        expected = youtube.YouTubeDailyDataset(
            channel_id="UC123",
            channel_title="Example Channel",
            metric_date="2026-08-20",
            videos=[],
            metrics_by_video={},
        )
        config = SimpleNamespace()

        with patch.object(
            youtube,
            "_fetch_analytics_dataset",
            return_value=expected,
            create=True,
        ) as fetch:
            result = asyncio.run(youtube.fetch_daily_dataset(config))

        self.assertIs(result, expected)
        fetch.assert_called_once_with(config)

    def test_credential_refresh_logs_start_and_completion_without_secrets(self) -> None:
        youtube = _youtube_module()

        class FakeCredentials:
            token = "short-lived-access-token"
            expiry = "2026-08-20T12:00:00Z"

            def __init__(self, **_kwargs: object) -> None:
                pass

            def refresh(self, _request: object) -> None:
                pass

        config = SimpleNamespace(
            youtube_client_id="client-id",
            youtube_client_secret="client-secret",
            youtube_refresh_token="refresh-token",
            youtube_channel_id="UC123",
        )
        with (
            patch.object(youtube, "Credentials", FakeCredentials),
            patch.object(youtube, "GoogleRequest", return_value=object()),
            self.assertLogs("app.services.social_media.youtube", level="INFO") as captured,
        ):
            credentials = youtube._refresh_credentials(config)

        self.assertIsInstance(credentials, FakeCredentials)
        messages = "\n".join(captured.output)
        self.assertIn("youtube.credentials.refresh.start", messages)
        self.assertIn("youtube.credentials.refresh.done", messages)
        self.assertNotIn("refresh-token", messages)
        self.assertNotIn("client-secret", messages)

    def test_oauth_channel_lookup_uses_official_sdk(self) -> None:
        youtube = _youtube_module()
        sdk_client = object()
        with (
            patch.object(youtube, "build", return_value=sdk_client) as build_client,
            patch.object(
                youtube,
                "_fetch_channel_sdk",
                return_value=("UC123", "Example", "uploads"),
            ) as fetch_channel,
            self.assertLogs("app.services.social_media.youtube", level="INFO") as captured,
        ):
            result = youtube._fetch_oauth_channel_with_sdk("temporary-access-token")

        self.assertEqual(result, ("UC123", "Example", "uploads"))
        build_client.assert_called_once()
        self.assertEqual(build_client.call_args.args[:2], ("youtube", "v3"))
        fetch_channel.assert_called_once_with(sdk_client)
        messages = "\n".join(captured.output)
        self.assertIn("youtube.oauth.channel_request.start", messages)
        self.assertIn("youtube.oauth.channel_request.done", messages)
        self.assertNotIn("temporary-access-token", messages)

    def test_callback_never_reports_connected_when_persistence_is_not_visible(self) -> None:
        from app.routers.social_media import analytics as social_media
        from app.services.social_media.config import SocialMediaConfig

        disconnected = SocialMediaConfig(
            schedule_enabled=True,
            update_frequency="hourly",
            schedule_time="09:00",
            timezone="UTC",
            youtube_client_id="client-id",
            youtube_client_secret="client-secret",
            youtube_refresh_token=None,
            youtube_channel_id=None,
            youtube_channel_title=None,
            oauth_state="expected-state",
            oauth_redirect_uri="https://public.example/api/social-media/youtube/oauth/callback",
            last_run_at=None,
            next_run_at=None,
        )
        request = Request(
            {
                "type": "http",
                "scheme": "https",
                "server": ("public.example", 443),
                "client": ("203.0.113.5", 12345),
                "headers": [(b"host", b"public.example")],
            }
        )

        with (
            patch.object(social_media, "load_social_media_config", return_value=disconnected),
            patch.object(social_media, "update_social_media_config", return_value=disconnected),
            patch.object(
                social_media,
                "exchange_oauth_code",
                new=AsyncMock(return_value=("refresh-token", "UC123", "Example Channel")),
            ),
        ):
            response = asyncio.run(
                social_media.youtube_oauth_callback(
                    request,
                    code="authorization-code",
                    state="expected-state",
                    error=None,
                )
            )
            status = social_media._settings_out()

        self.assertFalse(status.youtube_connected)
        self.assertIn("youtube=error", response.headers["location"])

    def test_callback_persists_connection_before_reporting_connected_and_logs_trace(self) -> None:
        from app.routers.social_media import analytics as social_media
        from app.services.settings import runtime_config
        from app.services.social_media.config import (
            load_social_media_config,
            update_social_media_config,
        )

        request = Request(
            {
                "type": "http",
                "scheme": "https",
                "server": ("public.example", 443),
                "client": ("203.0.113.5", 12345),
                "headers": [
                    (b"host", b"public.example"),
                    (b"x-forwarded-host", b"public.example"),
                ],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            control_db_path = Path(directory) / "control.db"
            with patch.object(runtime_config, "CONTROL_DB_PATH", control_db_path):
                load_social_media_config()
                update_social_media_config(
                    youtube_client_id="client-id",
                    youtube_client_secret="client-secret",
                    oauth_state="expected-state",
                    oauth_redirect_uri=(
                        "https://public.example/api/social-media/youtube/oauth/callback"
                    ),
                )
                with (
                    patch.object(
                        social_media,
                        "exchange_oauth_code",
                        new=AsyncMock(
                            return_value=("refresh-token", "UC123", "Example Channel")
                        ),
                    ),
                    self.assertLogs("app.routers.social_media.analytics", level="INFO") as captured,
                ):
                    response = asyncio.run(
                        social_media.youtube_oauth_callback(
                            request,
                            code="authorization-code",
                            state="expected-state",
                            error=None,
                        )
                    )
                    status = social_media._settings_out()

        messages = "\n".join(captured.output)
        self.assertTrue(status.youtube_connected)
        self.assertEqual(status.youtube_channel_id, "UC123")
        self.assertIn("youtube=connected", response.headers["location"])
        self.assertIn("social_media.oauth.callback.connected trace_id=", messages)
        self.assertIn("social_media.connection.status_read youtube_connected=True", messages)
        for secret in ("authorization-code", "expected-state", "refresh-token", "client-secret"):
            self.assertNotIn(secret, messages)

    def test_deployment_public_origin_is_persisted_and_normalized(self) -> None:
        from app.services.settings.deployment_config import (
            load_deployment_config,
            normalize_public_origin,
            save_public_origin,
        )
        from app.services.settings import runtime_config

        with tempfile.TemporaryDirectory() as directory:
            control_db_path = Path(directory) / "control.db"
            with patch.object(runtime_config, "CONTROL_DB_PATH", control_db_path):
                save_public_origin("https://sparkling.nimbus2000.site:8443/")
                self.assertEqual(
                    load_deployment_config().public_origin,
                    "https://sparkling.nimbus2000.site:8443",
                )
        with self.assertRaises(ValueError):
            normalize_public_origin("https://sparkling.nimbus2000.site:8443/api")
        with self.assertRaises(ValueError):
            normalize_public_origin("http://sparkling.nimbus2000.site:8443")

    def test_oauth_redirect_uses_runtime_public_origin(self) -> None:
        from app.routers.social_media import analytics as social_media

        app = FastAPI()
        app.include_router(social_media.router, prefix="/api/social-media")
        request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("sparkling", 3721),
                "client": ("172.18.0.3", 12345),
                "headers": [(b"host", b"sparkling:3721")],
                "app": app,
            }
        )
        deployment = SimpleNamespace(public_origin="https://sparkling.nimbus2000.site:8443")
        configured = SimpleNamespace(dev_origin="")

        with (
            patch.object(social_media, "load_deployment_config", return_value=deployment, create=True),
            patch.object(social_media, "app_config", configured),
        ):
            redirect_uri = social_media._youtube_oauth_redirect_uri(request)

        self.assertEqual(
            redirect_uri,
            "https://sparkling.nimbus2000.site:8443/api/social-media/youtube/oauth/callback",
        )

    def test_oauth_redirect_requires_runtime_origin_in_production(self) -> None:
        from app.routers.social_media import analytics as social_media

        app = FastAPI()
        app.include_router(social_media.router, prefix="/api/social-media")
        request = Request(
            {
                "type": "http",
                "scheme": "http",
                "server": ("sparkling", 3721),
                "client": ("172.18.0.3", 12345),
                "headers": [(b"host", b"sparkling:3721")],
                "app": app,
            }
        )

        with (
            patch.object(
                social_media,
                "load_deployment_config",
                return_value=SimpleNamespace(public_origin=None),
            ),
            patch.object(social_media, "app_config", SimpleNamespace(dev_origin="")),
            self.assertRaisesRegex(ValueError, "Public URL"),
        ):
            social_media._youtube_oauth_redirect_uri(request)

    def test_automatic_query_runs_one_hour_later(self) -> None:
        from app.services.social_media.collector import calculate_next_run_at

        now = datetime(2026, 8, 19, 10, 15, 30)
        next_run = calculate_next_run_at("hourly", "09:00", "Asia/Shanghai", now)

        self.assertEqual(next_run, now + timedelta(hours=1))

    def test_log_redaction_keeps_context_without_credentials(self) -> None:
        from app.logger import redact_log_text

        redacted = redact_log_text(
            "Authorization: Bearer token.value client_secret=secret refresh_token=refresh "
            "code=oauth-code state=oauth-state channel_id=UC123"
        )

        for secret in ("token.value", "=secret", "=refresh", "oauth-code", "oauth-state"):
            self.assertNotIn(secret, redacted)
        self.assertIn("channel_id=UC123", redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
