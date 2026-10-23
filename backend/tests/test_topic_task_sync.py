"""双向关联、日期及看板状态的回归用例，需显式执行。"""
from datetime import datetime, timezone
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ContentTopic, UserTask
from app.routers.tasks import BoardMove, TaskCreate, TaskPatch, create_task, move_board_task, update_task
from app.routers.social_media.topics import (
    TopicCreate, TopicPatch, create_topic, update_topic, list_available_topics, series_options, task_options,
)


class TopicTaskSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_link_existing_task_and_preserve_local_time(self) -> None:
        task = create_task(TaskCreate(title="task", category="自媒体"), self.session)
        topic = create_topic(TopicCreate(title="topic", scheduled_at=datetime(2020, 1, 1, 12, 30, tzinfo=timezone.utc)), self.session)
        linked = update_topic(topic.id, TopicPatch(task_id=task.id, status="working", timezone="Asia/Shanghai"), self.session)
        self.assertEqual(linked.task_id, task.id)
        self.assertEqual(self.session.get(UserTask, task.id).due_date, "2020-01-01")
        update_task(task.id, TaskPatch(due_date="2020-01-03", timezone="Asia/Shanghai"), self.session)
        self.assertEqual(self.session.get(ContentTopic, topic.id).scheduled_at, datetime(2020, 1, 3, 12, 30))
        update_task(task.id, TaskPatch(due_date=None, timezone="Asia/Shanghai"), self.session)
        self.assertIsNone(self.session.get(ContentTopic, topic.id).scheduled_at)

    def test_publication_uses_actual_time_and_reopens_both_sides(self) -> None:
        topic = create_topic(TopicCreate(title="topic", status="working", timezone="Asia/Shanghai"), self.session)
        published = datetime(2020, 1, 1, 18, 15, tzinfo=timezone.utc)
        update_topic(topic.id, TopicPatch(status="published", published_at=published, timezone="Asia/Shanghai"), self.session)
        task = self.session.get(UserTask, topic.task_id)
        self.assertEqual(task.actual_completion_date, "2020-01-02")
        completed_at = task.completed_at
        update_task(task.id, TaskPatch(actual_completion_date="2020-01-04", timezone="Asia/Shanghai"), self.session)
        self.assertEqual(task.completed_at, completed_at)
        self.assertEqual(self.session.get(ContentTopic, topic.id).published_at, datetime(2020, 1, 3, 18, 15))
        update_task(task.id, TaskPatch(completed=False, timezone="Asia/Shanghai"), self.session)
        self.assertEqual(self.session.get(ContentTopic, topic.id).status, "working")
        self.assertIsNone(self.session.get(ContentTopic, topic.id).published_at)
        move_board_task(task.id, BoardMove(status="next", timezone="Asia/Shanghai"), self.session)
        self.assertEqual(self.session.get(ContentTopic, topic.id).status, "not_started")
        update_topic(topic.id, TopicPatch(status="working", timezone="Asia/Shanghai"), self.session)
        self.assertEqual(task.board_status, "doing")

    def test_candidates_and_series(self) -> None:
        topic = create_topic(TopicCreate(title="topic", series="  系列 A  "), self.session)
        create_topic(TopicCreate(title="published", status="published", series="系列 A"), self.session)
        self.assertEqual(series_options(self.session), ["系列 A"])
        self.assertEqual([item.id for item in list_available_topics(self.session)], [topic.id])
        task = create_task(TaskCreate(title="task", category="自媒体", topic_id=topic.id), self.session)
        self.assertEqual(list_available_topics(self.session), [])
        self.assertEqual(task_options(self.session), [])
        other = create_topic(TopicCreate(title="other"), self.session)
        with self.assertRaises(HTTPException):
            update_topic(other.id, TopicPatch(task_id=task.id), self.session)
        self.assertEqual(self.session.get(ContentTopic, topic.id).task_id, task.id)

    def test_task_can_select_unlinked_working_topic(self) -> None:
        topic = ContentTopic(title="legacy", status="working")
        self.session.add(topic)
        self.session.commit()
        self.assertEqual([item.id for item in list_available_topics(self.session)], [topic.id])
        task = create_task(TaskCreate(title="task", category="自媒体", topic_id=topic.id), self.session)
        self.assertEqual(topic.task_id, task.id)


if __name__ == "__main__":
    unittest.main()
