from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-trend-rss-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-trend-rss-control.db")
open(_TEST_DB_PATH, "a", encoding="utf-8").close()
os.environ.setdefault("SPARKLING_DB_PATH", _TEST_DB_PATH)
os.environ.setdefault("SPARKLING_CONTROL_DB_PATH", _TEST_CONTROL_DB_PATH)


def _app_modules():
    from app import db, models
    from app.routers import settings as settings_router
    from app.routers import trends as trends_router
    from app.services.trend import cleanup, collector, sources

    return db, models, settings_router, trends_router, cleanup, collector, sources


class TrendRssAndDeletionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        db, _models, _settings_router, _trends_router, _cleanup, _collector, _sources = _app_modules()
        db.Base.metadata.drop_all(bind=db.get_engine())
        db.Base.metadata.create_all(bind=db.get_engine())

    async def test_rss_parser_reads_atom_and_respects_limit(self) -> None:
        _db, _models, _settings_router, _trends_router, _cleanup, _collector, sources = _app_modules()
        feed = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Example</title>
          <entry><title>First</title><link href="https://example.com/first"/><summary>One</summary></entry>
          <entry><title>Second</title><link href="https://example.com/second"/><summary>Two</summary></entry>
        </feed>"""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=feed, request=request)

        source = sources.RssSourceConfig(
            id="rss-1",
            name="Example Feed",
            url="https://example.com/feed.xml",
            limit=1,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidates = await sources._fetch_rss(client, source)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].title, "First")
        self.assertEqual(candidates[0].url, "https://example.com/first")
        self.assertEqual(candidates[0].source, "rss:Example Feed")
        self.assertEqual(candidates[0].metadata["rss_source_id"], "rss-1")

    def test_rss_source_crud_is_persisted(self) -> None:
        db, models, settings_router, _trends_router, _cleanup, _collector, _sources = _app_modules()
        with db.SessionLocal() as session:
            created = settings_router.create_trend_rss_source(
                settings_router.TrendRssSourceCreate(
                    name="Example",
                    url="https://example.com/feed.xml",
                    item_limit=12,
                ),
                session,
            )
            updated = settings_router.update_trend_rss_source(
                created.id,
                settings_router.TrendRssSourceUpdate(name="Renamed", enabled=False),
                session,
            )
            stored = session.get(models.TrendRssSource, created.id)

            self.assertIsNotNone(stored)
            self.assertEqual(updated.name, "Renamed")
            self.assertFalse(updated.enabled)
            self.assertEqual(updated.item_limit, 12)

            with self.assertRaises(HTTPException) as duplicate:
                settings_router.create_trend_rss_source(
                    settings_router.TrendRssSourceCreate(
                        name="Duplicate",
                        url="https://example.com/feed.xml",
                    ),
                    session,
                )
            self.assertEqual(duplicate.exception.status_code, 409)

            settings_router.delete_trend_rss_source(created.id, session)
            self.assertIsNone(session.get(models.TrendRssSource, created.id))

    async def test_rss_source_test_reports_processable_and_invalid_data(self) -> None:
        db, _models, settings_router, _trends_router, _cleanup, _collector, sources = _app_modules()
        with db.SessionLocal() as session:
            created = settings_router.create_trend_rss_source(
                settings_router.TrendRssSourceCreate(
                    name="Example",
                    url="https://example.com/feed.xml",
                ),
                session,
            )
            candidate = sources.TrendCandidate(
                source="rss:Example",
                title="Processable item",
                url="https://example.com/article",
            )
            with patch.object(settings_router, "fetch_rss_source", AsyncMock(return_value=[candidate])):
                successful = await settings_router.test_trend_rss_source(
                    created.id,
                    settings_router.TrendRssSourceTestRequest(),
                    session,
                )
            with patch.object(settings_router, "fetch_rss_source", AsyncMock(return_value=[])):
                invalid = await settings_router.test_trend_rss_source(
                    created.id,
                    settings_router.TrendRssSourceTestRequest(),
                    session,
                )

        self.assertTrue(successful.ok)
        self.assertEqual(successful.candidate_count, 1)
        self.assertEqual(successful.samples[0].title, "Processable item")
        self.assertFalse(invalid.ok)
        self.assertIn("数据结构不正确", invalid.message)

    async def test_rss_only_collection_skips_query_planning(self) -> None:
        db, models, _settings_router, _trends_router, _cleanup, collector, _sources = _app_modules()
        with db.SessionLocal() as session:
            settings = models.Settings(
                id=1,
                trend_model="fake-model",
                trend_source_config=json.dumps(
                    {
                        "github": {"enabled": False, "limit": 8},
                        "hackernews": {"enabled": False, "limit": 8},
                        "google": {"enabled": False, "limit": 8},
                    }
                ),
            )
            source = models.TrendRssSource(
                name="Example",
                url="https://example.com/feed.xml",
                enabled=True,
                item_limit=5,
            )
            run = models.TrendRun(trigger="manual", status="pending")
            session.add_all([settings, source, run])
            session.commit()
            run_id = run.id

        planner = AsyncMock(return_value=["should not run"])
        discovery = AsyncMock(return_value=[])
        with (
            patch.object(collector, "plan_search_queries", planner),
            patch.object(collector, "_discover_candidates_from_queries", discovery),
        ):
            result = await collector.collect_trends(run_id)

        planner.assert_not_awaited()
        self.assertEqual(result, {"candidate_count": 0, "saved_count": 0})
        rss_sources = discovery.await_args.args[2]
        self.assertEqual(len(rss_sources), 1)
        self.assertEqual(rss_sources[0].name, "Example")

    def test_soft_deleted_trend_is_hidden_then_purged_after_30_days(self) -> None:
        db, models, _settings_router, trends_router, cleanup, _collector, _sources = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            item = models.TrendItem(
                title="Disposable",
                score=90,
                fingerprint="disposable",
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            session.commit()
            item_id = item.id

            trends_router.delete_trend(item_id, session)
            hidden = trends_router.list_trends(
                q=None,
                category=None,
                tag=None,
                source=None,
                limit=100,
                offset=0,
                session=session,
            )
            self.assertEqual(hidden.total, 0)
            self.assertIsNotNone(session.get(models.TrendItem, item_id))

            self.assertEqual(cleanup.purge_expired_deleted_trends(session, now + timedelta(days=29)), 0)
            self.assertEqual(cleanup.purge_expired_deleted_trends(session, now + timedelta(days=31)), 1)
            self.assertIsNone(session.get(models.TrendItem, item_id))


if __name__ == "__main__":
    unittest.main()
