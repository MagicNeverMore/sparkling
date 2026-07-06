from __future__ import annotations

import unittest
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-session-lifetime-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(
    tempfile.gettempdir(),
    "sparkling-session-lifetime-control.db",
)
open(_TEST_DB_PATH, "a", encoding="utf-8").close()
os.environ.setdefault("SPARKLING_DB_PATH", _TEST_DB_PATH)
os.environ.setdefault("SPARKLING_CONTROL_DB_PATH", _TEST_CONTROL_DB_PATH)

from app.models import AtomEmbedding, ThoughtAtom, ThoughtLink
from app.services import embedding, linker
from app.services.settings_snapshot import EmbeddingSettingsSnapshot, LinkSettingsSnapshot


class _SessionTracker:
    def __init__(self) -> None:
        self.active = 0
        self.max_active_during_external_await = 0

    def note_external_await(self) -> None:
        self.max_active_during_external_await = max(
            self.max_active_during_external_await,
            self.active,
        )


class _EmbeddingSession:
    def __init__(self, tracker: _SessionTracker, existing=None) -> None:  # noqa: ANN001
        self._tracker = tracker
        self._existing = existing
        self.added = []
        self.commits = 0

    def __enter__(self):
        self._tracker.active += 1
        return self

    def __exit__(self, *_exc_info):
        self._tracker.active -= 1

    def get(self, model, _key):  # noqa: ANN001
        if model is ThoughtAtom:
            return SimpleNamespace(
                id="atom-1",
                content="slow embedding text",
                status="inbox",
                version=1,
            )
        if model is AtomEmbedding:
            return self._existing
        return None

    def add(self, value) -> None:  # noqa: ANN001
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1


class _LinkQuery:
    def filter_by(self, **_kwargs):  # noqa: ANN003
        return self

    def first(self):
        return None


class _LinkSession:
    def __init__(self, tracker: _SessionTracker) -> None:
        self._tracker = tracker
        self.added = []
        self.commits = 0

    def __enter__(self):
        self._tracker.active += 1
        return self

    def __exit__(self, *_exc_info):
        self._tracker.active -= 1

    def get(self, model, _key):  # noqa: ANN001
        if model is ThoughtAtom:
            return SimpleNamespace(id="atom-1", status="inbox", version=1)
        return None

    def query(self, model):  # noqa: ANN001
        if model is ThoughtLink:
            return _LinkQuery()
        raise AssertionError(f"unexpected query model: {model}")

    def add(self, value) -> None:  # noqa: ANN001
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1


class _BroadcastManager:
    def __init__(self, tracker: _SessionTracker) -> None:
        self._tracker = tracker
        self.events = []

    async def broadcast(self, event_type: str, data: dict) -> None:
        self._tracker.note_external_await()
        self.events.append((event_type, data))


class SessionLifetimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_api_call_does_not_hold_session(self) -> None:
        tracker = _SessionTracker()
        settings = EmbeddingSettingsSnapshot(
            embed_base_url="http://example.test/v1",
            embed_api_key="test",
            embed_model="test-embedding",
            embed_dim=3,
        )

        async def fake_embed_texts(_settings, _texts):  # noqa: ANN001
            tracker.note_external_await()
            return [[0.1, 0.2, 0.3]]

        with (
            patch.object(embedding, "SessionLocal", lambda: _EmbeddingSession(tracker)),
            patch.object(embedding, "embed_texts", fake_embed_texts),
            patch.object(embedding, "get_vector", return_value=None),
            patch.object(embedding, "upsert_vector"),
        ):
            result = await embedding.sync_atom_embedding("atom-1", settings, expected_version=1)

        self.assertTrue(result)
        self.assertEqual(tracker.max_active_during_external_await, 0)
        self.assertEqual(tracker.active, 0)

    async def test_current_embedding_still_counts_as_success_without_api_call(self) -> None:
        tracker = _SessionTracker()
        settings = EmbeddingSettingsSnapshot(
            embed_base_url="http://example.test/v1",
            embed_api_key="test",
            embed_model="test-embedding",
            embed_dim=3,
        )
        existing = SimpleNamespace(
            atom_version=1,
            content_hash=embedding.atom_content_hash("slow embedding text"),
        )

        async def fail_if_called(_settings, _texts):  # noqa: ANN001
            raise AssertionError("embedding API should not be called")

        with (
            patch.object(embedding, "SessionLocal", lambda: _EmbeddingSession(tracker, existing)),
            patch.object(embedding, "embed_texts", fail_if_called),
            patch.object(embedding, "get_vector", return_value=b"vector"),
        ):
            result = await embedding.sync_atom_embedding("atom-1", settings, expected_version=1)

        self.assertTrue(result)
        self.assertEqual(tracker.active, 0)

    async def test_link_broadcast_does_not_hold_session(self) -> None:
        tracker = _SessionTracker()
        settings = LinkSettingsSnapshot(
            link_threshold_auto=0.85,
            link_threshold_suggest=0.70,
        )
        manager = _BroadcastManager(tracker)

        with (
            patch.object(linker, "SessionLocal", lambda: _LinkSession(tracker)),
            patch.object(linker, "knn_by_existing_embedding", return_value=[("atom-2", 0.9)]),
        ):
            events = await linker.discover_links("atom-1", settings, manager, expected_version=1)

        self.assertEqual(len(events), 1)
        self.assertEqual(tracker.max_active_during_external_await, 0)
        self.assertEqual(tracker.active, 0)


if __name__ == "__main__":
    unittest.main()
