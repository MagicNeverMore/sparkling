"""看板移动与排序回归用例，需显式运行。"""
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import UserTask
from app.routers.tasks import BoardMove, TaskCreate, create_task, move_board_task


class TaskBoardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.tasks = [create_task(TaskCreate(title=str(i)), self.session) for i in range(3)]

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_default_move_and_reorder(self) -> None:
        self.assertTrue(all(task.board_status == "backlog" for task in self.tasks))
        for task in self.tasks:
            move_board_task(task.id, BoardMove(status="next"), self.session)
        result = move_board_task(self.tasks[2].id, BoardMove(status="next", before_id=self.tasks[0].id), self.session)
        ordered = sorted((task for task in result if task.board_status == "next"), key=lambda task: task.board_position)
        self.assertEqual([task.id for task in ordered], [self.tasks[2].id, self.tasks[0].id, self.tasks[1].id])
        result = move_board_task(self.tasks[2].id, BoardMove(status="doing"), self.session)
        moved = next(task for task in result if task.id == self.tasks[2].id)
        self.assertEqual(moved.board_status, "doing")
        self.assertIsNone(moved.start_date)

    def test_stale_target_does_not_change_state(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            move_board_task(self.tasks[0].id, BoardMove(status="next", before_id="missing"), self.session)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.session.get(UserTask, self.tasks[0].id).board_status, "backlog")

    def test_completed_task_cannot_move(self) -> None:
        task = self.session.get(UserTask, self.tasks[0].id)
        task.completed = True
        self.session.commit()
        with self.assertRaises(HTTPException) as caught:
            move_board_task(task.id, BoardMove(status="doing"), self.session)
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
