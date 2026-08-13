from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-trend-query-planning-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-trend-query-planning-control.db")
open(_TEST_DB_PATH, "a", encoding="utf-8").close()
os.environ.setdefault("SPARKLING_DB_PATH", _TEST_DB_PATH)
os.environ.setdefault("SPARKLING_CONTROL_DB_PATH", _TEST_CONTROL_DB_PATH)


def _app_modules():
    from app import db, models
    from app.services.trend import collector
    from app.services.trend.sources import TrendCandidate

    return db, models, collector, TrendCandidate


class _FakeClient:
    def __init__(self) -> None:
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True


def _completion(content: str | None, *, reasoning_content: str | None = None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, reasoning_content=reasoning_content),
                finish_reason="stop",
            )
        ]
    )


class TrendQueryPlanningTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        db, _models, _collector, _TrendCandidate = _app_modules()
        db.Base.metadata.drop_all(bind=db.get_engine())
        db.Base.metadata.create_all(bind=db.get_engine())

    async def test_planner_uses_full_brand_brain_and_returns_valid_queries(self) -> None:
        _db, models, collector, _TrendCandidate = _app_modules()
        settings = models.Settings(trend_model="fake-model")
        prompt = "关注热点： - AI; -自动化; -Technology Trend; -software startups"
        source_config = {"github": {"enabled": True, "limit": 8}}

        captured_messages = []
        captured_max_tokens = []

        async def fake_completion(_client, **kwargs):  # noqa: ANN001
            captured_messages.extend(kwargs["messages"])
            captured_max_tokens.append(kwargs["max_tokens"])
            return _completion('{"queries": ["AI automation", "Technology Trend software startups"]}')

        with (
            patch.object(collector, "_get_trend_client", return_value=(_FakeClient(), "fake-model")),
            patch.object(collector, "_create_json_chat_completion", fake_completion),
        ):
            queries = await collector.plan_search_queries(settings, prompt, source_config)

        self.assertEqual(queries, ["AI automation", "Technology Trend software startups"])
        self.assertIn(prompt, captured_messages[-1]["content"])
        self.assertEqual(captured_max_tokens, [1600])

    async def test_planner_rejects_empty_queries(self) -> None:
        _db, models, collector, _TrendCandidate = _app_modules()
        settings = models.Settings(trend_model="fake-model")

        with (
            patch.object(collector, "_get_trend_client", return_value=(_FakeClient(), "fake-model")),
            patch.object(collector, "_create_json_chat_completion", AsyncMock(return_value=_completion('{"queries": []}'))),
            self.assertRaisesRegex(ValueError, "搜索 query 生成失败"),
        ):
            await collector.plan_search_queries(settings, "关注热点：AI", {"github": {"enabled": True, "limit": 8}})

    async def test_planner_rejects_invalid_json(self) -> None:
        _db, models, collector, _TrendCandidate = _app_modules()
        settings = models.Settings(trend_model="fake-model")

        with (
            patch.object(collector, "_get_trend_client", return_value=(_FakeClient(), "fake-model")),
            patch.object(collector, "_create_json_chat_completion", AsyncMock(return_value=_completion("not json"))),
            self.assertRaisesRegex(ValueError, "LLM 返回不是有效 JSON"),
        ):
            await collector.plan_search_queries(settings, "关注热点：AI", {"github": {"enabled": True, "limit": 8}})

    async def test_planner_uses_reasoning_content_when_content_is_empty(self) -> None:
        _db, models, collector, _TrendCandidate = _app_modules()
        settings = models.Settings(trend_model="fake-model")

        with (
            patch.object(collector, "_get_trend_client", return_value=(_FakeClient(), "fake-model")),
            patch.object(
                collector,
                "_create_json_chat_completion",
                AsyncMock(return_value=_completion(None, reasoning_content='{"queries": ["AI automation"]}')),
            ),
        ):
            queries = await collector.plan_search_queries(
                settings,
                "关注热点：AI",
                {"github": {"enabled": True, "limit": 8}},
            )

        self.assertEqual(queries, ["AI automation"])

    async def test_evaluator_reserves_tokens_for_reasoning_and_json_output(self) -> None:
        _db, models, collector, TrendCandidate = _app_modules()
        settings = models.Settings(trend_model="fake-model")
        evidence = [
            collector.TrendEvidence(
                candidate=TrendCandidate(source="github", title="AI automation", url="https://example.com/repo"),
                fetched=collector.WebFetchResult(
                    url="https://example.com/repo",
                    final_url="https://example.com/repo",
                    ok=True,
                    title="AI automation",
                    text="A developer tool for AI automation.",
                ),
            )
        ]
        captured_max_tokens = []

        async def fake_completion(_client, **kwargs):  # noqa: ANN001
            captured_max_tokens.append(kwargs["max_tokens"])
            return _completion('{"score": 90, "title": "AI automation"}')

        with (
            patch.object(collector, "_get_trend_client", return_value=(_FakeClient(), "fake-model")),
            patch.object(collector, "_create_json_chat_completion", fake_completion),
        ):
            result = await collector._evaluate_evidence(settings, "关注热点：AI", evidence)

        self.assertEqual(result["score"], 90)
        self.assertEqual(captured_max_tokens, [3200])

    async def test_discovery_uses_planned_queries_and_dedupes_candidates(self) -> None:
        _db, _models, collector, TrendCandidate = _app_modules()
        calls: list[str] = []

        async def fake_discover(query, _source_config):  # noqa: ANN001
            calls.append(query)
            return [
                TrendCandidate(source="github", title=f"{query} first", url="https://example.com/same"),
                TrendCandidate(source="hackernews", title=f"{query} second", url=f"https://example.com/{query}"),
            ]

        with patch.object(collector, "discover_candidates", fake_discover):
            candidates = await collector._discover_candidates_from_queries(
                ["AI automation", "Technology Trend software startups"],
                {"github": {"enabled": True, "limit": 8}},
            )

        self.assertEqual(calls, ["AI automation", "Technology Trend software startups"])
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].url, "https://example.com/same")

    async def test_collect_trends_scores_with_full_brand_brain(self) -> None:
        db, models, collector, TrendCandidate = _app_modules()
        prompt = "关注热点： - AI; -自动化; -Technology Trend; -software startups"
        with db.SessionLocal() as session:
            settings = models.Settings(
                id=1,
                trend_brand_prompt=prompt,
                trend_model="fake-model",
                trend_score_threshold=70,
                trend_result_limit=20,
            )
            run = models.TrendRun(trigger="manual", status="pending")
            session.add_all([settings, run])
            session.commit()
            run_id = run.id

        captured_brand_prompt = []
        candidate = TrendCandidate(source="github", title="AI automation repo", url="https://example.com/repo")

        async def fake_score(_settings, brand_prompt, _evidence, _source_config, _seen_urls):  # noqa: ANN001
            captured_brand_prompt.append(brand_prompt)
            return {
                "title": "AI automation repo",
                "category": "AI",
                "score": 92,
                "scoring_reason": "Relevant",
                "core_insight": "AI automation is trending.",
                "content": "Draft content",
                "tags": ["AI", "automation"],
                "resources": [{"title": "AI automation repo", "url": "https://example.com/repo", "source": "github"}],
            }

        with (
            patch.object(collector, "plan_search_queries", AsyncMock(return_value=["AI automation"])),
            patch.object(collector, "_discover_candidates_from_queries", AsyncMock(return_value=[candidate])),
            patch.object(collector, "fetch_url_detail", AsyncMock(return_value=collector.WebFetchResult(url=candidate.url, final_url=candidate.url, ok=True, title=candidate.title))),
            patch.object(collector, "_score_with_follow_ups", fake_score),
        ):
            result = await collector.collect_trends(run_id)

        with db.SessionLocal() as session:
            run = session.get(models.TrendRun, run_id)
            items = session.query(models.TrendItem).all()

        self.assertEqual(result, {"candidate_count": 1, "saved_count": 1})
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.status, "done")
        self.assertEqual(captured_brand_prompt, [prompt])
        self.assertEqual(len(items), 1)

    async def test_collect_trends_marks_run_failed_when_planning_fails(self) -> None:
        db, models, collector, _TrendCandidate = _app_modules()
        with db.SessionLocal() as session:
            settings = models.Settings(id=1, trend_brand_prompt="关注热点：AI", trend_model="fake-model")
            run = models.TrendRun(trigger="manual", status="pending")
            session.add_all([settings, run])
            session.commit()
            run_id = run.id

        with (
            patch.object(collector, "plan_search_queries", AsyncMock(side_effect=ValueError("搜索 query 生成失败：LLM 没有返回可用 queries"))),
            self.assertRaisesRegex(ValueError, "搜索 query 生成失败"),
        ):
            await collector.collect_trends(run_id)

        with db.SessionLocal() as session:
            run = session.get(models.TrendRun, run_id)

        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.status, "failed")
        self.assertIn("搜索 query 生成失败", run.error or "")

    async def test_collect_trends_skips_a_candidate_when_scoring_fails(self) -> None:
        db, models, collector, TrendCandidate = _app_modules()
        with db.SessionLocal() as session:
            settings = models.Settings(id=1, trend_brand_prompt="关注热点：AI", trend_model="fake-model", trend_score_threshold=70)
            run = models.TrendRun(trigger="manual", status="pending")
            session.add_all([settings, run])
            session.commit()
            run_id = run.id

        candidates = [
            TrendCandidate(source="github", title="Broken candidate", url="https://example.com/broken"),
            TrendCandidate(source="github", title="Good candidate", url="https://example.com/good"),
        ]
        successful_result = {
            "title": "Good candidate",
            "category": "AI",
            "score": 90,
            "scoring_reason": "Relevant",
            "core_insight": "Useful trend.",
            "content": "Draft content",
            "tags": ["AI"],
            "resources": [],
        }

        async def fake_evidence(candidate):  # noqa: ANN001
            return collector.TrendEvidence(
                candidate=candidate,
                fetched=collector.WebFetchResult(url=candidate.url, final_url=candidate.url, ok=True, title=candidate.title),
            )

        with (
            patch.object(collector, "plan_search_queries", AsyncMock(return_value=["AI"])),
            patch.object(collector, "_discover_candidates_from_queries", AsyncMock(return_value=candidates)),
            patch.object(collector, "_build_evidence", fake_evidence),
            patch.object(
                collector,
                "_score_with_follow_ups",
                AsyncMock(side_effect=[ValueError("invalid JSON"), successful_result]),
            ),
        ):
            result = await collector.collect_trends(run_id)

        with db.SessionLocal() as session:
            run = session.get(models.TrendRun, run_id)
            items = session.query(models.TrendItem).all()

        self.assertEqual(result, {"candidate_count": 2, "saved_count": 1})
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run.status, "done")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Good candidate")


if __name__ == "__main__":
    unittest.main()
