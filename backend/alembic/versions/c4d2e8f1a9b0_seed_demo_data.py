"""seed demo data

Revision ID: c4d2e8f1a9b0
Revises: a3f1c2d8e9b7
Create Date: 2026-06-29 09:30:00.000000

"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d2e8f1a9b0"
down_revision: Union[str, Sequence[str], None] = "a3f1c2d8e9b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEMO_ATOM_IDS = [f"demo-atom-{i:02d}" for i in range(1, 16)]
DEMO_LINK_IDS = [f"demo-link-{i:02d}" for i in range(1, 21)]
DEMO_TASK_IDS = [f"demo-task-{i:02d}" for i in range(1, 6)]


def _ts(minutes_ago: int) -> datetime:
    return datetime.utcnow() - timedelta(minutes=minutes_ago)


def upgrade() -> None:
    thought_atom = sa.table(
        "thought_atom",
        sa.column("id", sa.String()),
        sa.column("content", sa.Text()),
        sa.column("content_type", sa.String()),
        sa.column("media_urls", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("source_device", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("device_id", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
        sa.column("deleted_at", sa.DateTime()),
    )
    thought_link = sa.table(
        "thought_link",
        sa.column("id", sa.String()),
        sa.column("from_atom_id", sa.String()),
        sa.column("to_atom_id", sa.String()),
        sa.column("link_type", sa.String()),
        sa.column("confidence", sa.Float()),
        sa.column("source", sa.String()),
        sa.column("user_confirmed", sa.Boolean()),
        sa.column("user_ignored", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )
    user_task = sa.table(
        "user_task",
        sa.column("id", sa.String()),
        sa.column("title", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("start_date", sa.String()),
        sa.column("due_date", sa.String()),
        sa.column("completed", sa.Boolean()),
        sa.column("completed_at", sa.DateTime()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )

    atoms = [
        ("demo-atom-01", "晨跑前 5 分钟动态热身，比直接开跑更容易找到节奏感。", 1),
        ("demo-atom-02", "低强度有氧最好保持在心率二区，能跑很久但还能完整说话。", 7),
        ("demo-atom-03", "配速不应该每天硬拉，轻松跑的意义是给身体留恢复空间。", 18),
        ("demo-atom-04", "出汗多的时候只补水不补电解质，后半程更容易头晕和脱水。", 120),
        ("demo-atom-05", "晨跑让我一天更清醒，夜跑反而容易把神经系统激活到睡不着。", 300),
        ("demo-atom-06", "番茄钟不是为了制造紧张感，而是给开始工作一个足够低的门槛。", 420),
        ("demo-atom-07", "Deep Work 的关键是提前定义清楚产出物，不然只是长时间坐在电脑前。", 540),
        ("demo-atom-08", "上下文切换的成本比想象大，切出去一次就要重新加载任务状态。", 1440),
        ("demo-atom-09", "专注力恢复需要真正离屏，刷短视频不是休息，是继续消耗注意力。", 1500),
        ("demo-atom-10", "写作的肌肉记忆来自每天固定时间开一个空白文档，先写烂也没关系。", 2880),
        ("demo-atom-11", "阅读速率不是越快越好，能复述核心问题才说明真的读进去了。", 2940),
        ("demo-atom-12", "笔记复习最好隔几天回看一次，把当时的高亮改写成自己的判断。", 4320),
        ("demo-atom-13", "咖啡机又开始漏水，可能是密封圈老化，需要周末拆开看看。", 5760),
        ("demo-atom-14", "周末想去江边走走，顺便找一家安静的店整理下个月计划。", 7200),
        ("demo-atom-15", "昨晚梦到老同学一起赶火车，醒来只记得站台特别亮。", 8640),
    ]
    op.bulk_insert(
        thought_atom,
        [
            {
                "id": atom_id,
                "content": content,
                "content_type": "text",
                "media_urls": None,
                "status": "active" if index < 12 else "inbox",
                "source_device": "demo-seed",
                "version": 1,
                "device_id": "demo",
                "created_at": _ts(minutes_ago),
                "updated_at": _ts(minutes_ago),
                "deleted_at": None,
            }
            for index, (atom_id, content, minutes_ago) in enumerate(atoms)
        ],
    )

    links = [
        ("demo-link-01", "demo-atom-01", "demo-atom-02", 0.93, "ai_auto", True),
        ("demo-link-02", "demo-atom-01", "demo-atom-03", 0.90, "ai_auto", True),
        ("demo-link-03", "demo-atom-02", "demo-atom-03", 0.88, "ai_auto", True),
        ("demo-link-04", "demo-atom-04", "demo-atom-05", 0.86, "ai_auto", True),
        ("demo-link-05", "demo-atom-07", "demo-atom-08", 0.91, "ai_auto", True),
        ("demo-link-06", "demo-atom-10", "demo-atom-12", 0.84, "user", True),
        ("demo-link-07", "demo-atom-06", "demo-atom-07", 0.82, "user", True),
        ("demo-link-08", "demo-atom-11", "demo-atom-12", 0.80, "user", True),
        ("demo-link-09", "demo-atom-01", "demo-atom-04", 0.77, "ai_suggested", False),
        ("demo-link-10", "demo-atom-02", "demo-atom-04", 0.74, "ai_suggested", False),
        ("demo-link-11", "demo-atom-02", "demo-atom-05", 0.72, "ai_suggested", False),
        ("demo-link-12", "demo-atom-03", "demo-atom-05", 0.69, "ai_suggested", False),
        ("demo-link-13", "demo-atom-06", "demo-atom-08", 0.76, "ai_suggested", False),
        ("demo-link-14", "demo-atom-06", "demo-atom-09", 0.73, "ai_suggested", False),
        ("demo-link-15", "demo-atom-07", "demo-atom-09", 0.79, "ai_suggested", False),
        ("demo-link-16", "demo-atom-08", "demo-atom-09", 0.83, "ai_suggested", False),
        ("demo-link-17", "demo-atom-10", "demo-atom-11", 0.75, "ai_suggested", False),
        ("demo-link-18", "demo-atom-05", "demo-atom-09", 0.66, "ai_suggested", False),
        ("demo-link-19", "demo-atom-12", "demo-atom-14", 0.62, "ai_suggested", False),
        ("demo-link-20", "demo-atom-08", "demo-atom-10", 0.68, "ai_suggested", False),
    ]
    op.bulk_insert(
        thought_link,
        [
            {
                "id": link_id,
                "from_atom_id": from_atom_id,
                "to_atom_id": to_atom_id,
                "link_type": "semantic",
                "confidence": confidence,
                "source": source,
                "user_confirmed": user_confirmed,
                "user_ignored": False,
                "created_at": _ts(30 + index),
            }
            for index, (link_id, from_atom_id, to_atom_id, confidence, source, user_confirmed) in enumerate(links)
        ],
    )

    now = datetime.utcnow()
    op.bulk_insert(
        user_task,
        [
            {
                "id": "demo-task-01",
                "title": "整理跑步笔记成一篇复盘",
                "description": "把心率二区、动态热身和补电解质这几条想法串起来。",
                "category": "writing",
                "start_date": "2026-06-29",
                "due_date": "2026-07-02",
                "completed": False,
                "completed_at": None,
                "created_at": now - timedelta(hours=4),
                "updated_at": now - timedelta(hours=4),
            },
            {
                "id": "demo-task-02",
                "title": "为 Sparkling 录一段演示素材",
                "description": "展示快速输入、AI 关联建议、图谱浏览和任务拆解。",
                "category": "demo",
                "start_date": "2026-06-29",
                "due_date": "2026-07-01",
                "completed": False,
                "completed_at": None,
                "created_at": now - timedelta(hours=3),
                "updated_at": now - timedelta(hours=3),
            },
            {
                "id": "demo-task-03",
                "title": "检查 macOS app 数据目录",
                "description": "确认打包后使用 Application Support 下的数据库路径。",
                "category": "app_dev",
                "start_date": "2026-06-30",
                "due_date": "2026-07-03",
                "completed": False,
                "completed_at": None,
                "created_at": now - timedelta(hours=2),
                "updated_at": now - timedelta(hours=2),
            },
            {
                "id": "demo-task-04",
                "title": "把阅读高亮改写成自己的判断",
                "description": "回看三天前的笔记，只保留能复述核心问题的条目。",
                "category": "review",
                "start_date": "2026-06-28",
                "due_date": "2026-06-29",
                "completed": True,
                "completed_at": now - timedelta(minutes=45),
                "created_at": now - timedelta(days=1),
                "updated_at": now - timedelta(minutes=45),
            },
            {
                "id": "demo-task-05",
                "title": "周末拆咖啡机检查密封圈",
                "description": "如果只是密封圈老化，记录型号并下单替换件。",
                "category": "life",
                "start_date": "2026-07-04",
                "due_date": "2026-07-05",
                "completed": False,
                "completed_at": None,
                "created_at": now - timedelta(days=2),
                "updated_at": now - timedelta(days=2),
            },
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()

    def delete_by_ids(table: str, column: str, ids: list[str]) -> None:
        stmt = sa.text(f"DELETE FROM {table} WHERE {column} IN :ids").bindparams(
            sa.bindparam("ids", expanding=True),
        )
        bind.execute(stmt, {"ids": ids})

    delete_by_ids("thought_link", "id", DEMO_LINK_IDS)
    delete_by_ids("atom_embedding", "atom_id", DEMO_ATOM_IDS)
    delete_by_ids("thought_atom", "id", DEMO_ATOM_IDS)
    delete_by_ids("user_task", "id", DEMO_TASK_IDS)
