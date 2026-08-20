from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

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

    async def test_social_media_orphan_task_recovers_missing_sync_run(self) -> None:
        db, models, task_queue, runner = _app_modules()
        from app.services.social_media import collector
        from app.services.social_media.youtube import YouTubeDailyDataset

        run_id = "missing-social-media-run"
        with db.SessionLocal() as session:
            task = task_queue.enqueue(
                session,
                "social_media_collect",
                {"run_id": run_id},
                max_attempts=1,
            )
            task_id = task.id

        config = SimpleNamespace(
            schedule_enabled=False,
            update_frequency="manual",
            schedule_time="09:00",
            timezone="UTC",
        )
        dataset = YouTubeDailyDataset(
            channel_id="UC-recovered",
            channel_title="Recovered channel",
            metric_date="2026-08-19",
            videos=[],
            metrics_by_video={},
        )
        with (
            patch.object(collector, "load_social_media_config", return_value=config),
            patch.object(collector, "update_social_media_config"),
            patch.object(collector, "fetch_daily_dataset", new=AsyncMock(return_value=dataset)),
        ):
            processed = await runner._drain_pending_tasks_once(worker_id="test-worker")

        with db.SessionLocal() as session:
            task = session.get(models.TaskQueue, task_id)
            run = session.get(models.SocialMediaSyncRun, run_id)

        self.assertEqual(processed, 1)
        self.assertIsNotNone(task)
        self.assertIsNotNone(run)
        assert task is not None
        assert run is not None
        self.assertEqual(task.status, "done")
        self.assertEqual(run.status, "done")
        self.assertEqual(run.external_account_id, "UC-recovered")

    def test_manual_social_media_request_queues_without_creating_run(self) -> None:
        db, models, _task_queue, _runner = _app_modules()
        from app.routers import social_media

        app = FastAPI()
        app.include_router(social_media.router, prefix="/api/social-media")
        config = SimpleNamespace(youtube_connected=True, youtube_channel_id="UC-manual")

        with (
            patch.object(social_media, "load_social_media_config", return_value=config),
            TestClient(app) as client,
        ):
            response = client.post("/api/social-media/sync")
            latest = client.get("/api/social-media/runs/latest")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["trigger"], "manual")
        self.assertEqual(response.json()["status"], "queued")
        self.assertIsNone(latest.json())
        with db.SessionLocal() as session:
            self.assertEqual(session.query(models.TaskQueue).count(), 1)
            self.assertEqual(session.query(models.SocialMediaSyncRun).count(), 0)

    def test_repeated_manual_social_media_requests_reuse_only_manual_task(self) -> None:
        db, models, _task_queue, _runner = _app_modules()
        from app.routers import social_media

        app = FastAPI()
        app.include_router(social_media.router, prefix="/api/social-media")
        config = SimpleNamespace(youtube_connected=True, youtube_channel_id="UC-manual")

        with (
            patch.object(social_media, "load_social_media_config", return_value=config),
            TestClient(app) as client,
        ):
            first = client.post("/api/social-media/sync")
            second = client.post("/api/social-media/sync")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["task_id"], second.json()["task_id"])
        with db.SessionLocal() as session:
            self.assertEqual(session.query(models.TaskQueue).count(), 1)

    def test_database_rejects_duplicate_active_social_media_trigger(self) -> None:
        db, models, task_queue, _runner = _app_modules()
        with db.SessionLocal() as session:
            first = task_queue.enqueue(
                session,
                "social_media_collect",
                {"trigger": "manual"},
                resource_key="social_media:youtube",
                dedupe_key="social_media:manual",
                max_attempts=1,
            )
            first_id = first.id
            with self.assertRaises(IntegrityError):
                task_queue.enqueue(
                    session,
                    "social_media_collect",
                    {"trigger": "manual"},
                    resource_key="social_media:youtube",
                    dedupe_key="social_media:manual",
                    max_attempts=1,
                )
            session.rollback()
            tasks = session.query(models.TaskQueue).all()

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, first_id)

    def test_database_rejects_two_running_tasks_for_same_resource(self) -> None:
        db, models, _task_queue, _runner = _app_modules()
        with db.SessionLocal() as session:
            session.add_all(
                [
                    models.TaskQueue(
                        task_type="social_media_collect",
                        payload='{"trigger": "manual"}',
                        status="running",
                        attempts=1,
                        resource_key="social_media:youtube",
                    ),
                    models.TaskQueue(
                        task_type="social_media_collect",
                        payload='{"trigger": "scheduled"}',
                        status="running",
                        attempts=1,
                        resource_key="social_media:youtube",
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()

    def test_due_schedule_creates_task_independent_from_pending_manual_task(self) -> None:
        db, models, _task_queue, _runner = _app_modules()
        from app.services.social_media import collector

        now = datetime(2026, 8, 20, 4, 0, 0)
        config = SimpleNamespace(
            schedule_enabled=True,
            update_frequency="hourly",
            youtube_connected=True,
            next_run_at="2026-08-20T03:00:00Z",
            schedule_time="09:00",
            timezone="UTC",
        )
        with db.SessionLocal() as session:
            manual = collector.enqueue_social_media_task(session, "manual")
            with (
                patch.object(collector, "load_social_media_config", return_value=config),
                patch.object(collector, "update_social_media_config"),
            ):
                scheduled = collector.maybe_enqueue_due_social_media_task(session, now)

            tasks = session.query(models.TaskQueue).order_by(models.TaskQueue.priority.desc()).all()

        self.assertIsNotNone(scheduled)
        assert scheduled is not None
        self.assertNotEqual(manual.id, scheduled.id)
        self.assertEqual([task.priority for task in tasks], [100, 0])
        self.assertIn('"trigger": "manual"', tasks[0].payload)
        self.assertIn('"trigger": "scheduled"', tasks[1].payload)

    async def test_social_media_run_exists_only_while_worker_executes_task(self) -> None:
        db, models, _task_queue, runner = _app_modules()
        from app.services.social_media import collector
        from app.services.social_media.youtube import YouTubeDailyDataset

        with db.SessionLocal() as session:
            collector.enqueue_social_media_task(session, "manual")

        fetch_started = asyncio.Event()
        release_fetch = asyncio.Event()
        config = SimpleNamespace(
            schedule_enabled=False,
            update_frequency="manual",
            schedule_time="09:00",
            timezone="UTC",
        )
        dataset = YouTubeDailyDataset(
            channel_id="UC-running",
            channel_title="Running channel",
            metric_date="2026-08-19",
            videos=[],
            metrics_by_video={},
        )

        async def delayed_fetch(_config):  # noqa: ANN001
            fetch_started.set()
            await release_fetch.wait()
            return dataset

        with (
            patch.object(collector, "load_social_media_config", return_value=config),
            patch.object(collector, "update_social_media_config") as update_config,
            patch.object(collector, "fetch_daily_dataset", side_effect=delayed_fetch),
        ):
            worker = asyncio.create_task(runner._drain_pending_tasks_once(worker_id="test-worker"))
            await asyncio.wait_for(fetch_started.wait(), timeout=1)
            with db.SessionLocal() as session:
                running = session.query(models.SocialMediaSyncRun).one()
                running_task = session.query(models.TaskQueue).one()
                self.assertEqual(running.trigger, "manual")
                self.assertEqual(running.status, "running")
                self.assertIsNotNone(running.started_at)
                self.assertIsNone(running.finished_at)
                self.assertIn(f'"run_id": "{running.id}"', running_task.payload)

            release_fetch.set()
            await worker

        update_kwargs = update_config.call_args.kwargs
        self.assertNotIn("next_run_at", update_kwargs)

        with db.SessionLocal() as session:
            completed = session.query(models.SocialMediaSyncRun).one()
            self.assertEqual(completed.status, "done")

    async def test_reports_not_ready_ends_scheduled_run_without_retrying_same_task(self) -> None:
        db, models, _task_queue, runner = _app_modules()
        from app.services.social_media import collector
        from app.services.social_media.youtube import YouTubeReportsNotReadyError

        with db.SessionLocal() as session:
            task = collector.enqueue_social_media_task(session, "scheduled")
            task_id = task.id

        config = SimpleNamespace()
        error = YouTubeReportsNotReadyError(
            basic_count=1,
            reach_count=0,
            basic_dates=["2026-08-19"],
            reach_dates=[],
        )
        with (
            patch.object(collector, "load_social_media_config", return_value=config),
            patch.object(collector, "fetch_daily_dataset", new=AsyncMock(side_effect=error)),
            self.assertLogs("app.workers.runner", level="WARNING") as captured,
        ):
            await runner._drain_pending_tasks_once(worker_id="test-worker")

        with db.SessionLocal() as session:
            failed_task = session.get(models.TaskQueue, task_id)
            failed_run = session.query(models.SocialMediaSyncRun).one()

        assert failed_task is not None
        self.assertEqual(failed_task.status, "failed")
        self.assertEqual(failed_task.attempts, 1)
        self.assertEqual(failed_run.trigger, "scheduled")
        self.assertEqual(failed_run.status, "failed")
        self.assertIsNotNone(failed_run.finished_at)
        messages = "\n".join(captured.output)
        self.assertIn("本次同步失败", messages)
        self.assertNotIn("retry_after_seconds", messages)

        next_hour_config = SimpleNamespace(
            schedule_enabled=True,
            update_frequency="hourly",
            youtube_connected=True,
            next_run_at="2026-08-20T05:00:00Z",
            schedule_time="09:00",
            timezone="UTC",
        )
        with db.SessionLocal() as session:
            with (
                patch.object(collector, "load_social_media_config", return_value=next_hour_config),
                patch.object(collector, "update_social_media_config"),
            ):
                next_task = collector.maybe_enqueue_due_social_media_task(
                    session,
                    datetime(2026, 8, 20, 5, 0, 0),
                )
            self.assertIsNotNone(next_task)
            assert next_task is not None
            self.assertNotEqual(next_task.id, task_id)
            self.assertEqual(session.query(models.TaskQueue).count(), 2)
            self.assertEqual(session.query(models.SocialMediaSyncRun).count(), 1)

    def test_expired_social_media_lease_ends_running_run(self) -> None:
        db, models, _task_queue, runner = _app_modules()
        now = datetime.utcnow()
        run = models.SocialMediaSyncRun(
            trigger="scheduled",
            status="running",
            started_at=now - timedelta(minutes=20),
        )
        with db.SessionLocal() as session:
            session.add(run)
            session.flush()
            task = models.TaskQueue(
                task_type="social_media_collect",
                payload=f'{{"trigger": "scheduled", "run_id": "{run.id}"}}',
                status="running",
                attempts=1,
                max_attempts=1,
                resource_key="social_media:youtube",
                lease_until=now - timedelta(seconds=1),
                created_at=now - timedelta(minutes=20),
                updated_at=now - timedelta(minutes=20),
            )
            session.add(task)
            session.commit()
            run_id = run.id
            task_id = task.id

        reclaimed = runner._reclaim_expired_task_leases()

        with db.SessionLocal() as session:
            failed_task = session.get(models.TaskQueue, task_id)
            failed_run = session.get(models.SocialMediaSyncRun, run_id)

        self.assertEqual(reclaimed, 1)
        assert failed_task is not None
        assert failed_run is not None
        self.assertEqual(failed_task.status, "failed")
        self.assertEqual(failed_run.status, "failed")
        self.assertIsNotNone(failed_run.finished_at)

    def test_expired_social_media_lease_does_not_overwrite_completed_run(self) -> None:
        db, models, _task_queue, runner = _app_modules()
        now = datetime.utcnow()
        run = models.SocialMediaSyncRun(
            trigger="manual",
            status="done",
            started_at=now - timedelta(minutes=20),
            finished_at=now - timedelta(minutes=10),
        )
        with db.SessionLocal() as session:
            session.add(run)
            session.flush()
            task = models.TaskQueue(
                task_type="social_media_collect",
                payload=f'{{"trigger": "manual", "run_id": "{run.id}"}}',
                status="running",
                attempts=1,
                max_attempts=1,
                resource_key="social_media:youtube",
                lease_until=now - timedelta(seconds=1),
            )
            session.add(task)
            session.commit()
            run_id = run.id

        runner._reclaim_expired_task_leases()

        with db.SessionLocal() as session:
            completed_run = session.get(models.SocialMediaSyncRun, run_id)
        assert completed_run is not None
        self.assertEqual(completed_run.status, "done")

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
                "retryable_test_task",
                {},
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
