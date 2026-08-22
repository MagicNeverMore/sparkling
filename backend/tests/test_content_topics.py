"""选题库与任务双向联动测试。"""
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ContentTopic, UserTask
from app.routers.social_media.topics import TopicCreate, TopicPatch, create_topic, update_topic
from app.routers.tasks import TaskCreate, create_task, delete_task


class ContentTopicTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()

    def tearDown(self) -> None:
        self.session.close()

    def test_working_topic_creates_task_and_published_completes_it(self) -> None:
        topic = create_topic(
            TopicCreate(
                title="视频选题",
                series="产品拆解",
                status="working",
                scheduled_at=datetime(2026, 8, 21, 16, tzinfo=timezone.utc),
                timezone="Asia/Shanghai",
            ),
            self.session,
        )
        task = self.session.get(UserTask, topic.task_id)
        self.assertIsNotNone(task)
        self.assertEqual(topic.series, "产品拆解")
        self.assertEqual(task.category, "自媒体")
        self.assertEqual(task.due_date, "2026-08-22")

        update_topic(topic.id, TopicPatch(status="published", timezone="Asia/Shanghai"), self.session)
        self.assertTrue(self.session.get(UserTask, topic.task_id).completed)

    def test_new_social_media_task_can_link_not_started_topic(self) -> None:
        topic = ContentTopic(
            title="反向联动",
            scheduled_at=datetime(2026, 8, 21, 16),
        )
        self.session.add(topic)
        self.session.commit()

        task = create_task(
            TaskCreate(title="制作视频", category="自媒体", topic_id=topic.id, timezone="Asia/Shanghai"),
            self.session,
        )
        self.session.refresh(topic)
        self.assertEqual(topic.status, "working")
        self.assertEqual(topic.task_id, task.id)
        self.assertEqual(task.due_date, "2026-08-22")

        delete_task(task.id, self.session)
        self.session.refresh(topic)
        self.assertIsNone(topic.task_id)


if __name__ == "__main__":
    unittest.main()
