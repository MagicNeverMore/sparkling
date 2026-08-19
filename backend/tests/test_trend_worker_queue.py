from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from types import ModuleType
from unittest.mock import patch

_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-worker-queue-test.db")
_TEST_CONTROL_DB_PATH = os.path.join(tempfile.gettempdir(), "sparkling-worker-queue-control.db")
open(_TEST_DB_PATH, "a", encoding="utf-8").close()
os.environ.setdefault("SPARKLING_DB_PATH", _TEST_DB_PATH)
os.environ.setdefault("SPARKLING_CONTROL_DB_PATH", _TEST_CONTROL_DB_PATH)


def _app_modules() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    from app import db, models
    from app.services import task_queue
    from app.workers import runner

    return db, models, task_queue, runner


class TrendWorkerQueueTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        db, _models, _task_queue, _runner = _app_modules()
        db.Base.metadata.drop_all(bind=db.get_engine())
        db.Base.metadata.create_all(bind=db.get_engine())

    async def test_trend_task_is_not_blocked_by_embedding_settings(self) -> None:
        db, models, _task_queue, runner = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            embed_task = models.TaskQueue(
                task_type="embed",
                payload='{"atom_id": "atom-1"}',
                status="pending",
                attempts=0,
                created_at=now - timedelta(minutes=1),
            )
            trend_task = models.TaskQueue(
                task_type="trend_collect",
                payload='{"run_id": "run-1"}',
                status="pending",
                attempts=0,
                created_at=now,
            )
            session.add_all([embed_task, trend_task])
            session.commit()
            embed_task_id = embed_task.id
            trend_task_id = trend_task.id

        handled_payloads: list[dict] = []

        async def fake_handle_trend_collect(payload: dict) -> None:
            handled_payloads.append(payload)

        with patch.object(runner, "_handle_trend_collect", fake_handle_trend_collect):
            processed = await runner._drain_pending_tasks_once()

        with db.SessionLocal() as session:
            embed_task = session.get(models.TaskQueue, embed_task_id)
            trend_task = session.get(models.TaskQueue, trend_task_id)
            self.assertIsNotNone(embed_task)
            self.assertIsNotNone(trend_task)
            assert embed_task is not None
            assert trend_task is not None
            self.assertEqual(embed_task.status, "pending")
            self.assertEqual(embed_task.attempts, 0)
            self.assertEqual(trend_task.status, "done")

        self.assertEqual(processed, 1)
        self.assertEqual(handled_payloads, [{"run_id": "run-1"}])

    async def test_timeout_does_not_leave_task_running(self) -> None:
        db, _models, task_queue, runner = _app_modules()
        with db.SessionLocal() as session:
            task = task_queue.enqueue(
                session,
                "trend_collect",
                {"run_id": "run-timeout"},
                max_attempts=1,
            )
            task_id = task.id

        with patch.dict(runner.TASK_TIMEOUT_SECONDS, {"trend_collect": 0.05}):
            claimed = runner._claim_task(worker_id="test-worker")
            self.assertIsNotNone(claimed)

            async def slow_collect(_payload: dict) -> None:
                await asyncio.sleep(1)

            with patch.object(runner, "_handle_trend_collect", slow_collect):
                await runner._run_claimed_task(claimed)

        with db.SessionLocal() as session:
            task = session.get(_models.TaskQueue, task_id)
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.status, "failed")
            self.assertIsNone(task.locked_by)
            self.assertIsNone(task.lease_until)

    def test_claim_skips_locked_resource(self) -> None:
        db, models, task_queue, _runner = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            session.add_all(
                [
                    models.TaskQueue(
                        task_type="embed",
                        payload='{"atom_id": "a"}',
                        status="running",
                        attempts=1,
                        max_attempts=3,
                        resource_key="atom:a",
                        lease_until=now + timedelta(minutes=5),
                        created_at=now - timedelta(minutes=3),
                        updated_at=now - timedelta(minutes=3),
                    ),
                    models.TaskQueue(
                        task_type="embed",
                        payload='{"atom_id": "a"}',
                        status="pending",
                        attempts=0,
                        max_attempts=3,
                        resource_key="atom:a",
                        available_at=now,
                        created_at=now - timedelta(minutes=2),
                        updated_at=now - timedelta(minutes=2),
                    ),
                    models.TaskQueue(
                        task_type="embed",
                        payload='{"atom_id": "b"}',
                        status="pending",
                        attempts=0,
                        max_attempts=3,
                        resource_key="atom:b",
                        available_at=now,
                        created_at=now - timedelta(minutes=1),
                        updated_at=now - timedelta(minutes=1),
                    ),
                ]
            )
            session.commit()
            claimed = task_queue.claim_next(
                session,
                worker_id="test-worker",
                lease_seconds=60,
            )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.resource_key, "atom:b")
        self.assertEqual(claimed.status, "running")

    def test_claim_respects_blocked_task_types(self) -> None:
        db, _models, task_queue, runner = _app_modules()
        with db.SessionLocal() as session:
            task_queue.enqueue(session, "embed", {"atom_id": "a"})
            claimed = task_queue.claim_next(
                session,
                worker_id="test-worker",
                lease_seconds=60,
                blocked_task_types=runner._blocked_task_types({"embed": 2}),
            )

        self.assertIsNone(claimed)

    def test_reclaim_expired_leases(self) -> None:
        db, models, task_queue, _runner = _app_modules()
        now = datetime.utcnow()
        with db.SessionLocal() as session:
            retry_task = models.TaskQueue(
                task_type="embed",
                payload='{"atom_id": "a"}',
                status="running",
                attempts=1,
                max_attempts=3,
                lease_until=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
            failed_task = models.TaskQueue(
                task_type="trend_collect",
                payload='{"run_id": "r"}',
                status="running",
                attempts=3,
                max_attempts=3,
                lease_until=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
            session.add_all([retry_task, failed_task])
            session.commit()
            retry_id = retry_task.id
            failed_id = failed_task.id
            reclaimed = task_queue.reclaim_expired_leases(session, now)
            retry_task = session.get(models.TaskQueue, retry_id)
            failed_task = session.get(models.TaskQueue, failed_id)

        self.assertEqual(reclaimed, 2)
        self.assertIsNotNone(retry_task)
        self.assertIsNotNone(failed_task)
        assert retry_task is not None
        assert failed_task is not None
        self.assertEqual(retry_task.status, "pending")
        self.assertEqual(failed_task.status, "failed")
        self.assertIsNone(retry_task.lease_until)
        self.assertIsNone(failed_task.lease_until)

    def test_mark_failed_sets_backoff(self) -> None:
        db, _models, task_queue, _runner = _app_modules()
        before = datetime.utcnow()
        with db.SessionLocal() as session:
            task = task_queue.enqueue(session, "embed", {"atom_id": "a"}, max_attempts=3)
            claimed = task_queue.claim_next(session, worker_id="test-worker", lease_seconds=60)
            assert claimed is not None
            status = task_queue.mark_failed(session, claimed.id, "boom")
            refreshed = session.get(_models.TaskQueue, task.id)

        self.assertEqual(status, "pending")
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.status, "pending")
        self.assertGreater(refreshed.available_at, before)
        self.assertIsNone(refreshed.locked_by)
        self.assertIsNone(refreshed.lease_until)

    def test_mark_failed_accepts_long_retry_delay(self) -> None:
        db, models, task_queue, _runner = _app_modules()
        before = datetime.utcnow()
        with db.SessionLocal() as session:
            task = task_queue.enqueue(
                session,
                "social_media_collect",
                {"run_id": "run-1"},
                max_attempts=48,
            )
            claimed = task_queue.claim_next(session, worker_id="test-worker", lease_seconds=60)
            assert claimed is not None
            status = task_queue.mark_failed(
                session,
                claimed.id,
                "reports not ready",
                retry_delay_seconds=3600,
            )
            refreshed = session.get(models.TaskQueue, task.id)

        self.assertEqual(status, "pending")
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.max_attempts, 48)
        self.assertGreaterEqual(refreshed.available_at, before + timedelta(minutes=59))


if __name__ == "__main__":
    unittest.main()
