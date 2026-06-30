"""ORM 模型。

注意：vec_atoms 是 sqlite-vec 虚表，不通过 SQLAlchemy 管理，
而是在 Settings 写入 embed_dim 后由 services/embedding.py 动态 CREATE。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class ThoughtAtom(Base):
    __tablename__ = "thought_atom"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String, default="text")  # text|voice|image|url|mixed
    media_urls: Mapped[str | None] = mapped_column(Text)  # JSON 数组
    status: Mapped[str] = mapped_column(String, default="inbox")  # inbox|active|archived|deleted
    source_device: Mapped[str | None] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)  # 乐观锁
    device_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column()


class AtomEmbedding(Base):
    """记录每条 atom 已生成 embedding 所用的模型与维度。
    实际向量数据在 sqlite-vec 虚表 vec_atoms 中。"""

    __tablename__ = "atom_embedding"

    atom_id: Mapped[str] = mapped_column(ForeignKey("thought_atom.id", ondelete="CASCADE"), primary_key=True)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    atom_version: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=_now, onupdate=_now)


class ThoughtLink(Base):
    __tablename__ = "thought_link"
    __table_args__ = (
        UniqueConstraint("from_atom_id", "to_atom_id", "link_type", name="uq_link"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    from_atom_id: Mapped[str] = mapped_column(ForeignKey("thought_atom.id", ondelete="CASCADE"), nullable=False)
    to_atom_id: Mapped[str] = mapped_column(ForeignKey("thought_atom.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String)  # semantic|temporal|manual|reference
    confidence: Mapped[float | None] = mapped_column(Float)  # 0..1
    source: Mapped[str] = mapped_column(String)  # ai_auto|ai_suggested|user
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    user_ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class TaskQueue(Base):
    """SQLite 任务队列，替代 Redis/ARQ。"""

    __tablename__ = "task_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # embed|link_discover|recluster
    payload: Mapped[str | None] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class UserTask(Base):
    """用户任务（自媒体发布计划、App 开发计划等）。"""

    __tablename__ = "user_task"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String)  # social_media|app_dev|other 或自定义
    start_date: Mapped[str | None] = mapped_column(String)  # 'YYYY-MM-DD'
    due_date: Mapped[str | None] = mapped_column(String)  # 'YYYY-MM-DD'
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Settings(Base):
    """单行配置表。"""

    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    embed_base_url: Mapped[str | None] = mapped_column(String)
    embed_api_key: Mapped[str | None] = mapped_column(String)
    embed_model: Mapped[str | None] = mapped_column(String)
    embed_dim: Mapped[int | None] = mapped_column(Integer)
    chat_base_url: Mapped[str | None] = mapped_column(String)
    chat_api_key: Mapped[str | None] = mapped_column(String)
    chat_model: Mapped[str | None] = mapped_column(String)
    link_threshold_auto: Mapped[float] = mapped_column(Float, default=0.85)
    link_threshold_suggest: Mapped[float] = mapped_column(Float, default=0.70)
