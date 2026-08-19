from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

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
