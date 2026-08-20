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

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-social-media-reporting-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(
    tempfile.gettempdir(),
    "sparkling-social-media-reporting-control.db",
)
os.environ["SPARKLING_DB_PATH"] = _TEST_DB_PATH
os.environ["SPARKLING_CONTROL_DB_PATH"] = _TEST_CONTROL_DB_PATH
Path(_TEST_DB_PATH).touch(exist_ok=True)


def _youtube_module() -> ModuleType:
    from app.services.social_media import youtube

    return youtube


def _report(metric_date: str, create_time: str, report_id: str) -> dict[str, str]:
    return {
        "id": report_id,
        "startTime": f"{metric_date}T08:00:00Z",
        "endTime": f"{metric_date}T08:00:00Z",
        "createTime": create_time,
        "downloadUrl": f"https://example.invalid/{report_id}",
    }


class SocialMediaReportingTest(unittest.TestCase):
    def test_callback_never_reports_connected_when_persistence_is_not_visible(self) -> None:
        from app.routers import social_media
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
            youtube_basic_job_id=None,
            youtube_reach_job_id=None,
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
        from app.routers import social_media
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
                    self.assertLogs("app.routers.social_media", level="INFO") as captured,
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
        from app.routers import social_media

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
        from app.routers import social_media

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

    def test_reports_not_ready_keeps_diagnostic_counts(self) -> None:
        youtube = _youtube_module()
        with self.assertRaises(youtube.YouTubeReportsNotReadyError) as caught:
            youtube._latest_common_reports(
                [_report("2026-08-18", "2026-08-19T10:00:00Z", "basic")],
                [],
            )

        self.assertEqual(caught.exception.basic_count, 1)
        self.assertEqual(caught.exception.reach_count, 0)
        self.assertEqual(caught.exception.retry_after_seconds, 3600)

    def test_latest_common_date_and_newest_version_are_selected(self) -> None:
        youtube = _youtube_module()
        older = _report("2026-08-18", "2026-08-19T10:00:00Z", "basic-old")
        newer = _report("2026-08-18", "2026-08-19T12:00:00Z", "basic-new")
        reach = _report("2026-08-18", "2026-08-19T11:00:00Z", "reach")

        metric_date, basic_report, reach_report = youtube._latest_common_reports(
            [older, newer],
            [reach],
        )

        self.assertEqual(metric_date, "2026-08-18")
        self.assertEqual(basic_report["id"], "basic-new")
        self.assertEqual(reach_report["id"], "reach")

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
