from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class LogReaderTest(unittest.TestCase):
    def test_reads_latest_filtered_lines_and_redacts_secrets(self) -> None:
        from app.services.settings import log_reader

        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            (log_dir / "sparkling.log").write_text(
                "2026-08-20 10:00:00 | INFO | app | started\n"
                "2026-08-20 10:01:00 | ERROR | app | access_token=secret-token failed\n"
                "2026-08-20 10:02:00 | ERROR | app | retry failed\n",
                encoding="utf-8",
            )
            with patch.object(log_reader, "LOG_DIR", log_dir):
                page = log_reader.read_log_page(
                    file_name="sparkling.log",
                    level="ERROR",
                    query="failed",
                    limit=1,
                )
                secret_page = log_reader.read_log_page(
                    file_name="sparkling.log",
                    query="access_token",
                )

        self.assertEqual(page["total_matches"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertIn("retry failed", page["items"][0]["text"])
        self.assertIsNotNone(page["next_before"])
        self.assertNotIn("secret-token", secret_page["items"][0]["text"])
        self.assertIn("[REDACTED]", secret_page["items"][0]["text"])

    def test_rejects_files_outside_managed_log_directory(self) -> None:
        from app.services.settings import log_reader

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(log_reader, "LOG_DIR", Path(directory)):
                with self.assertRaises(ValueError):
                    log_reader.read_log_page(file_name="../control.db")

    def test_lists_size_rotated_log_files(self) -> None:
        from app.services.settings import log_reader

        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            (log_dir / "sparkling.log.1").write_text("older\n", encoding="utf-8")
            with patch.object(log_reader, "LOG_DIR", log_dir):
                files = log_reader.list_log_files()

        self.assertEqual([item["name"] for item in files], ["sparkling.log.1"])


if __name__ == "__main__":
    unittest.main()
