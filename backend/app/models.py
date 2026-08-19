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
    """本地任务队列，替代 Redis/ARQ。"""

    __tablename__ = "task_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # embed|link_discover|recluster
    payload: Mapped[str | None] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime | None] = mapped_column(DateTime, default=_now)
    locked_by: Mapped[str | None] = mapped_column(String)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    resource_key: Mapped[str | None] = mapped_column(String)
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


class TrendItem(Base):
    """可作为自媒体内容选题的热点内容。"""

    __tablename__ = "trend_item"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float, default=0)
    scoring_reason: Mapped[str | None] = mapped_column(Text)
    core_insight: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[str | None] = mapped_column(Text)
    resources_json: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(default=_now)
    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    favorited_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class TrendRssSource(Base):
    """用户自定义的 RSS/Atom 信息源。"""

    __tablename__ = "trend_rss_source"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    item_limit: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class TrendRun(Base):
    """Trend 采集运行记录，用于页面展示和失败排查。"""

    __tablename__ = "trend_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    trigger: Mapped[str] = mapped_column(String, default="manual")  # manual|scheduled
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|done|failed
    error: Mapped[str | None] = mapped_column(Text)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    saved_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class SocialMediaDataset(Base):
    """某个平台账号在一个指标日期上的完整日级数据集。"""

    __tablename__ = "social_media_dataset"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_account_id",
            "metric_date",
            name="uq_social_media_dataset_account_date",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    external_account_id: Mapped[str] = mapped_column(String, nullable=False)
    metric_date: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD，provider 报告日期
    status: Mapped[str] = mapped_column(String, default="complete", nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class SocialMediaVideoSnapshot(Base):
    """数据集中一条 public 视频快照；同日重复同步时整批替换。"""

    __tablename__ = "social_media_video_snapshot"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_video_id", name="uq_social_media_video_dataset"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("social_media_dataset.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_video_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float | None] = mapped_column(Float)
    average_view_duration_seconds: Mapped[float | None] = mapped_column(Float)
    average_view_percentage: Mapped[float | None] = mapped_column(Float)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subscribers_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_subscribers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class SocialMediaSyncRun(Base):
    """采集运行日志；不会作为 List 的数据来源。"""

    __tablename__ = "social_media_sync_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String, default="youtube", nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String)
    trigger: Mapped[str] = mapped_column(String, default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    metric_date: Mapped[str | None] = mapped_column(String)
    video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
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
    trend_brand_prompt: Mapped[str | None] = mapped_column(Text)
    trend_base_url: Mapped[str | None] = mapped_column(String)
    trend_api_key: Mapped[str | None] = mapped_column(String)
    trend_model: Mapped[str | None] = mapped_column(String)
    trend_source_config: Mapped[str | None] = mapped_column(Text)
    trend_score_threshold: Mapped[float] = mapped_column(Float, default=70)
    trend_result_limit: Mapped[int] = mapped_column(Integer, default=20)
    trend_schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trend_schedule_frequency: Mapped[str] = mapped_column(String, default="daily")
    trend_schedule_mode: Mapped[str] = mapped_column(String, default="weekly")
    trend_schedule_days_json: Mapped[str | None] = mapped_column(Text)
    trend_schedule_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    trend_schedule_time: Mapped[str] = mapped_column(String, default="09:00")
    trend_timezone: Mapped[str] = mapped_column(String, default="UTC")
    trend_last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    trend_next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
