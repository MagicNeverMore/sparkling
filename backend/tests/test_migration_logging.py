from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine


class _ProbeHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class MigrationLoggingTest(unittest.TestCase):
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
