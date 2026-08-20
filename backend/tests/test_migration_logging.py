from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


class _ProbeHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class MigrationLoggingTest(unittest.TestCase):
    def test_social_media_pending_runs_are_finalized_and_rejected(self) -> None:
        from app.config import BACKEND_DIR

        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'migration.db'}")
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
            config.attributes["render_as_batch"] = True
            config.attributes["preserve_app_logging"] = True
            try:
                with engine.connect() as connection:
                    config.attributes["connection"] = connection
                    command.upgrade(config, "d1e2f3a4b5c6")
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            INSERT INTO social_media_sync_run (
                                id, platform, trigger, status, video_count, created_at, updated_at
                            ) VALUES (
                                'legacy-pending', 'youtube', 'scheduled', 'pending', 0,
                                '2026-08-20 00:00:00', '2026-08-20 00:00:00'
                            )
                            """
                        )
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO task_queue (
                                id, task_type, payload, status, attempts, max_attempts,
                                priority, locked_by, locked_at, lease_until, resource_key,
                                created_at, updated_at
                            ) VALUES (
                                'legacy-social-task', 'social_media_collect',
                                '{"run_id": "legacy-running"}', 'running', 8, 48,
                                0, 'old-worker', '2026-08-20 00:00:00',
                                '2026-08-20 01:00:00', 'social_media:youtube',
                                '2026-08-20 00:00:00', '2026-08-20 00:00:00'
                            )
                            """
                        )
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO social_media_sync_run (
                                id, platform, trigger, status, video_count, created_at, updated_at
                            ) VALUES (
                                'legacy-running', 'youtube', 'manual', 'running', 0,
                                '2026-08-20 00:00:00', '2026-08-20 00:00:00'
                            )
                            """
                        )
                    )
                with engine.connect() as connection:
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
                with engine.connect() as connection:
                    migrated = connection.execute(
                        text(
                            "SELECT status, finished_at FROM social_media_sync_run "
                            "WHERE id = 'legacy-pending'"
                        )
                    ).one()
                self.assertEqual(migrated.status, "failed")
                self.assertIsNotNone(migrated.finished_at)
                with engine.connect() as connection:
                    migrated_running = connection.execute(
                        text(
                            "SELECT status, finished_at FROM social_media_sync_run "
                            "WHERE id = 'legacy-running'"
                        )
                    ).one()
                self.assertEqual(migrated_running.status, "failed")
                self.assertIsNotNone(migrated_running.finished_at)
                with engine.connect() as connection:
                    migrated_task = connection.execute(
                        text(
                            "SELECT status, max_attempts, locked_by, lease_until "
                            "FROM task_queue WHERE id = 'legacy-social-task'"
                        )
                    ).one()
                self.assertEqual(migrated_task.status, "failed")
                self.assertEqual(migrated_task.max_attempts, 1)
                self.assertIsNone(migrated_task.locked_by)
                self.assertIsNone(migrated_task.lease_until)
                with self.assertRaises(IntegrityError), engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            INSERT INTO social_media_sync_run (
                                id, platform, trigger, status, video_count, created_at, updated_at
                            ) VALUES (
                                'new-pending', 'youtube', 'manual', 'pending', 0,
                                '2026-08-20 00:00:00', '2026-08-20 00:00:00'
                            )
                            """
                        )
                    )
            finally:
                engine.dispose()

    def test_embedded_migration_preserves_application_logging(self) -> None:
        from app.migrations import run_migrations_for_engine

        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        logger_states = {
            name: logger.disabled
            for name, logger in logging.Logger.manager.loggerDict.items()
            if isinstance(logger, logging.Logger)
        }
        probe = _ProbeHandler()
        root.addHandler(probe)

        try:
            with tempfile.TemporaryDirectory() as directory:
                engine = create_engine(f"sqlite:///{Path(directory) / 'migration.db'}")
                try:
                    run_migrations_for_engine(engine, render_as_batch=True)
                finally:
                    engine.dispose()

            self.assertIn(probe, root.handlers)
            self.assertTrue(
                any("Alembic migration 已升级到 head" in message for message in probe.messages)
            )
        finally:
            for handler in root.handlers:
                if handler not in original_handlers and handler is not probe:
                    handler.close()
            root.handlers = original_handlers
            root.setLevel(original_level)
            for name, disabled in logger_states.items():
                logger = logging.Logger.manager.loggerDict.get(name)
                if isinstance(logger, logging.Logger):
                    logger.disabled = disabled


if __name__ == "__main__":
    unittest.main()
