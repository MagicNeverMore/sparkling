from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


class SocialMediaSchemaMigrationTest(unittest.TestCase):
    def test_new_schema_replaces_legacy_snapshot_tables(self) -> None:
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
                    command.upgrade(config, "head")
                inspector = inspect(engine)
                tables = set(inspector.get_table_names())
                self.assertIn("social_media_video", tables)
                self.assertIn("social_media_video_metric", tables)
                self.assertNotIn("social_media_dataset", tables)
                self.assertNotIn("social_media_video_snapshot", tables)
                metric_columns = {
                    column["name"] for column in inspector.get_columns("social_media_video_metric")
                }
                self.assertTrue({"video_id", "data_date", "updated_at"} <= metric_columns)
            finally:
                engine.dispose()
