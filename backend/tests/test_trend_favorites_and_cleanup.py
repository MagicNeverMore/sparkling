from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-trend-favorites-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-trend-favorites-control.db")
open(_TEST_DB_PATH, "a", encoding="utf-8").close()
os.environ.setdefault("SPARKLING_DB_PATH", _TEST_DB_PATH)
os.environ.setdefault("SPARKLING_CONTROL_DB_PATH", _TEST_CONTROL_DB_PATH)


def _app_modules():
    from app import db, models
    from app.routers import trends
    from app.services.trend import cleanup

    return db, models, trends, cleanup


def _trend(models, title: str, now: datetime, *, days_ago: int = 0, favorited: bool = False):  # noqa: ANN001
    return models.TrendItem(
        title=title,
        score=90,
        fingerprint=title,
        first_seen_at=now - timedelta(days=days_ago),
        last_seen_at=now - timedelta(days=days_ago),
        favorited_at=now if favorited else None,
        is_favorited=favorited,
        created_at=now - timedelta(days=days_ago),
        updated_at=now - timedelta(days=days_ago),
    )


class TrendFavoritesAndCleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        db, _models, _trends, _cleanup = _app_modules()
        db.Base.metadata.drop_all(bind=db.get_engine())
        db.Base.metadata.create_all(bind=db.get_engine())

    def test_favorite_state_is_persisted_and_can_be_cleared(self) -> None:
        db, models, trends, _cleanup = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            item = _trend(models, "Favorite me", now)
            session.add(item)
            session.commit()
            trend_id = item.id

            favorited = trends.update_trend_favorite(
                trend_id,
                trends.TrendFavoriteUpdate(is_favorited=True),
                session,
            )
            self.assertTrue(favorited.is_favorited)
            self.assertIsNotNone(favorited.favorited_at)

            cleared = trends.update_trend_favorite(
                trend_id,
                trends.TrendFavoriteUpdate(is_favorited=False),
                session,
            )
            stored = session.get(models.TrendItem, trend_id)
            self.assertFalse(cleared.is_favorited)
            self.assertIsNone(cleared.favorited_at)
            self.assertFalse(stored.is_favorited)
            self.assertIsNone(stored.favorited_at)

    def test_auto_cleanup_skips_favorites_then_soft_deleted_items_are_purged(self) -> None:
        db, models, _trends, cleanup = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            stale = _trend(models, "Stale", now, days_ago=61)
            favorited = _trend(models, "Saved", now, days_ago=61, favorited=True)
            recent = _trend(models, "Recent", now, days_ago=59)
            session.add_all([stale, favorited, recent])
            session.commit()
            stale_id = stale.id
            favorited_id = favorited.id
            recent_id = recent.id

            self.assertEqual(cleanup.soft_delete_stale_unfavorited_trends(session, now), 1)
            self.assertIsNotNone(session.get(models.TrendItem, stale_id).deleted_at)
            self.assertIsNone(session.get(models.TrendItem, favorited_id).deleted_at)
            self.assertIsNone(session.get(models.TrendItem, recent_id).deleted_at)

            self.assertEqual(cleanup.purge_expired_deleted_trends(session, now + timedelta(days=29)), 0)
            self.assertEqual(cleanup.purge_expired_deleted_trends(session, now + timedelta(days=31)), 1)
            self.assertIsNone(session.get(models.TrendItem, stale_id))
            self.assertIsNotNone(session.get(models.TrendItem, favorited_id))

    def test_bulk_delete_soft_deletes_unique_active_items(self) -> None:
        db, models, trends, _cleanup = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            first = _trend(models, "First", now)
            second = _trend(models, "Second", now)
            already_deleted = _trend(models, "Deleted", now)
            already_deleted.deleted_at = now
            session.add_all([first, second, already_deleted])
            session.commit()

            result = trends.bulk_delete_trends(
                trends.TrendBulkDeleteRequest(ids=[first.id, second.id, first.id, already_deleted.id, "missing"]),
                session,
            )
            self.assertEqual(result.deleted_count, 2)
            self.assertEqual(set(result.deleted_ids), {first.id, second.id})
            self.assertIsNotNone(session.get(models.TrendItem, first.id).deleted_at)
            self.assertIsNotNone(session.get(models.TrendItem, second.id).deleted_at)


if __name__ == "__main__":
    unittest.main()
