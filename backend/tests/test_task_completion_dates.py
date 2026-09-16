"""完成日期、部分更新与操作时间的回归用例；仅显式运行时执行。"""
from datetime import datetime, timedelta
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import UserTask
from app.routers.social_media.topics import TopicCreate, TopicPatch, create_topic, update_topic
from app.routers.tasks import TaskCreate, TaskPatch, create_task, update_task
from app.services.task_dates import validate_task_dates
from app.time_utils import get_timezone, utc_naive_to_local


class TaskCompletionDatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_complete_correct_and_reopen(self) -> None:
        task = create_task(TaskCreate(title="task", start_date="2020-01-01",
                                      due_date="2020-01-03"), self.session)
        result = update_task(task.id, TaskPatch(completed=True,
                             actual_completion_date="2020-01-05"), self.session)
        timestamp = result.completed_at
        result = update_task(task.id, TaskPatch(actual_completion_date="2020-01-02"), self.session)
        self.assertEqual(result.completed_at, timestamp)
        self.assertEqual(result.actual_completion_date, "2020-01-02")
        result = update_task(task.id, TaskPatch(completed=False), self.session)
        self.assertIsNone(result.actual_completion_date)
        self.assertIsNone(result.completed_at)

    def test_null_clears_but_omission_preserves_dates(self) -> None:
        task = create_task(TaskCreate(title="task", start_date="2020-01-01",
                                      due_date="2020-01-03"), self.session)
        result = update_task(task.id, TaskPatch(title="renamed"), self.session)
        self.assertEqual(result.due_date, "2020-01-03")
        result = update_task(task.id, TaskPatch(start_date=None, due_date=None), self.session)
        self.assertIsNone(result.start_date)
        self.assertIsNone(result.due_date)

    def test_local_today_and_legacy_fallback(self) -> None:
        zone = "Pacific/Honolulu"
        task = create_task(TaskCreate(title="task", completed=True, timezone=zone), self.session)
        self.assertEqual(task.actual_completion_date, datetime.now(get_timezone(zone)).date().isoformat())
        stored = self.session.get(UserTask, task.id)
        stored.actual_completion_date = None
        stored.completed_at = datetime(2020, 1, 2, 1)
        self.session.commit()
        result = update_task(task.id, TaskPatch(title="legacy", timezone=zone), self.session)
        self.assertEqual(result.actual_completion_date, "2020-01-01")
        self.assertEqual(utc_naive_to_local(stored.completed_at, zone).date().isoformat(), result.actual_completion_date)

    def test_conflicting_patch_does_not_mutate_task(self) -> None:
        task = create_task(TaskCreate(title="original"), self.session)
        with self.assertRaises(HTTPException) as error:
            update_task(task.id, TaskPatch(title="changed", actual_completion_date="2020-01-01"), self.session)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.session.get(UserTask, task.id).title, "original")

    def test_topic_completion_uses_local_event_day_and_remains_editable(self) -> None:
        zone = "Asia/Shanghai"
        topic = create_topic(TopicCreate(title="topic", status="working", timezone=zone), self.session)
        update_topic(topic.id, TopicPatch(status="published", timezone=zone), self.session)
        task = self.session.get(UserTask, topic.task_id)
        self.assertEqual(task.actual_completion_date, utc_naive_to_local(task.completed_at, zone).date().isoformat())
        result = update_task(task.id, TaskPatch(actual_completion_date="2020-01-01", timezone=zone), self.session)
        self.assertEqual(result.actual_completion_date, "2020-01-01")

    def test_invalid_dates(self) -> None:
        tomorrow = (datetime.now(get_timezone("UTC")).date() + timedelta(days=1)).isoformat()
        cases = [
            ("2020-02-30", None, None, False),
            ("20200101", None, None, False),
            ("2020-01-03", "2020-01-02", None, False),
            ("2020-01-03", None, "2020-01-02", True),
            (None, None, tomorrow, True),
            (None, None, "2020-01-02", False),
            (None, None, None, True),
        ]
        for start, due, actual, completed in cases:
            with self.subTest(start=start, due=due, actual=actual), self.assertRaises(ValueError):
                validate_task_dates(start, due, actual, completed, "UTC")


if __name__ == "__main__":
    unittest.main()
