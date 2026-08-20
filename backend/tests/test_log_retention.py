from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class LogRetentionTest(unittest.TestCase):
    def test_prunes_oldest_managed_backups_to_directory_limit(self) -> None:
        from app import logger

        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            active = log_dir / "sparkling.log"
            oldest = log_dir / "sparkling.log.2026-08-18"
            newer = log_dir / "sparkling.log.1"
            unmanaged = log_dir / "keep.txt"
            active.write_bytes(b"a" * 40)
            oldest.write_bytes(b"b" * 40)
            newer.write_bytes(b"c" * 40)
            unmanaged.write_bytes(b"d" * 100)
            oldest.touch()
            newer.touch()

            removed = logger.prune_log_directory(log_dir, max_total_bytes=80)

            self.assertEqual(removed, [oldest.name])
            self.assertTrue(active.exists())
            self.assertTrue(newer.exists())
            self.assertTrue(unmanaged.exists())
            self.assertLessEqual(logger.managed_log_size(log_dir), 80)

    def test_size_rotating_handler_bounds_one_log_family(self) -> None:
        from app import logger

        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            handler = logger._SizeBoundRotatingFileHandler(
                filename=log_dir / "sparkling.log",
                maxBytes=128,
                backupCount=2,
                max_total_bytes=384,
            )
            test_logger = logger.logging.Logger("retention-test")
            test_logger.addHandler(handler)
            try:
                for _ in range(20):
                    test_logger.info("x" * 80)
            finally:
                handler.close()

            files = list(log_dir.glob("sparkling.log*"))
            self.assertLessEqual(len(files), 3)
            self.assertLessEqual(sum(path.stat().st_size for path in files), 384)


if __name__ == "__main__":
    unittest.main()
