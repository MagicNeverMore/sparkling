from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from app.services.trend import sources


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _repository(
    name: str,
    *,
    stars: int,
    forks: int,
    created_at: datetime,
    pushed_at: datetime,
) -> dict[str, object]:
    return {
        "name": name,
        "full_name": f"acme/{name}",
        "html_url": f"https://github.com/acme/{name}",
        "description": f"{name} description",
        "owner": {"login": "acme"},
        "stargazers_count": stars,
        "forks_count": forks,
        "open_issues_count": 3,
        "created_at": _timestamp(created_at),
        "pushed_at": _timestamp(pushed_at),
        "updated_at": _timestamp(pushed_at),
        "fork": False,
        "archived": False,
        "disabled": False,
    }


class TrendGithubHotnessTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_github_requires_recent_star_growth_and_sorts_by_it(self) -> None:
        now = datetime.now(timezone.utc)
        repositories = [
            _repository(
                "mature-hot",
                stars=2_000,
                forks=100,
                created_at=now - timedelta(days=120),
                pushed_at=now - timedelta(days=1),
            ),
            _repository(
                "new-hot",
                stars=300,
                forks=20,
                created_at=now - timedelta(days=10),
                pushed_at=now - timedelta(days=1),
            ),
            _repository(
                "tiny",
                stars=12,
                forks=1,
                created_at=now - timedelta(days=2),
                pushed_at=now - timedelta(days=1),
            ),
            _repository(
                "old-push",
                stars=3_000,
                forks=200,
                created_at=now - timedelta(days=120),
                pushed_at=now - timedelta(days=20),
            ),
        ]
        search_request: httpx.Request | None = None
        graph_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal search_request, graph_requests
            if request.url.path == "/search/repositories":
                search_request = request
                return httpx.Response(200, json={"items": repositories}, request=request)
            if request.url.path == "/graphql":
                graph_requests += 1
                self.assertEqual(request.headers["Authorization"], "Bearer test-token")
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "repo_0": {
                                "stargazers": {
                                    "edges": [{"starredAt": _timestamp(now - timedelta(days=1))} for _ in range(55)],
                                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                                }
                            },
                            "repo_1": {
                                "stargazers": {
                                    "edges": [{"starredAt": _timestamp(now - timedelta(days=1))} for _ in range(80)],
                                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                                }
                            },
                        }
                    },
                    request=request,
                )
            return httpx.Response(404, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidates = await sources._fetch_github(client, "AI agents", {"token": "test-token"}, limit=4)

        self.assertIsNotNone(search_request)
        assert search_request is not None
        search_query = search_request.url.params["q"]
        self.assertIn("pushed:>=", search_query)
        self.assertIn("stars:>=200", search_query)
        self.assertIn("forks:>=10", search_query)
        self.assertEqual(search_request.url.params["sort"], "stars")
        self.assertEqual(search_request.url.params["per_page"], "12")
        self.assertEqual(graph_requests, 1)
        self.assertEqual([candidate.title for candidate in candidates], ["acme/new-hot", "acme/mature-hot"])
        self.assertEqual(candidates[0].metadata["stars_last_7d"], 80)
        self.assertEqual(candidates[0].metadata["hotness_verification"], "star_velocity")

    async def test_mature_repository_can_pass_with_30_day_star_growth_from_second_page(self) -> None:
        now = datetime.now(timezone.utc)
        repository = _repository(
            "thirty-day-hot",
            stars=5_000,
            forks=500,
            created_at=now - timedelta(days=300),
            pushed_at=now - timedelta(days=1),
        )
        graph_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal graph_requests
            if request.url.path == "/search/repositories":
                return httpx.Response(200, json={"items": [repository]}, request=request)
            if request.url.path == "/graphql":
                graph_requests += 1
                query = json.loads(request.content)["query"]
                if "after:" not in query:
                    edges = [{"starredAt": _timestamp(now - timedelta(days=8))} for _ in range(100)]
                    page_info = {"endCursor": "next-page", "hasNextPage": True}
                else:
                    edges = [{"starredAt": _timestamp(now - timedelta(days=15))} for _ in range(50)]
                    page_info = {"endCursor": None, "hasNextPage": False}
                return httpx.Response(
                    200,
                    json={"data": {"repo_0": {"stargazers": {"edges": edges, "pageInfo": page_info}}}},
                    request=request,
                )
            return httpx.Response(404, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidates = await sources._fetch_github(client, "developer tools", {"token": "test-token"}, limit=1)

        self.assertEqual(graph_requests, 2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].metadata["stars_last_7d"], 0)
        self.assertEqual(candidates[0].metadata["stars_last_30d"], 150)

    async def test_without_token_uses_stricter_conservative_thresholds(self) -> None:
        now = datetime.now(timezone.utc)
        repositories = [
            _repository(
                "conservative-pass",
                stars=1_000,
                forks=50,
                created_at=now - timedelta(days=120),
                pushed_at=now - timedelta(days=1),
            ),
            _repository(
                "baseline-only",
                stars=500,
                forks=25,
                created_at=now - timedelta(days=120),
                pushed_at=now - timedelta(days=1),
            ),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/search/repositories")
            return httpx.Response(200, json={"items": repositories}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidates = await sources._fetch_github(client, "AI", {"token": None}, limit=8)

        self.assertEqual([candidate.title for candidate in candidates], ["acme/conservative-pass"])
        self.assertEqual(candidates[0].metadata["hotness_verification"], "conservative_without_token")
        self.assertIsNone(candidates[0].metadata["stars_last_7d"])


if __name__ == "__main__":
    unittest.main()
