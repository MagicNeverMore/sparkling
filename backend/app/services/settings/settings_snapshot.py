"""运行时 settings 快照。

ORM Settings 绑定在 Session 上。异步等待外部服务前先复制成不可变快照，
避免为了读取配置而长期占用数据库连接。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...models import Settings


@dataclass(frozen=True)
class EmbeddingSettingsSnapshot:
    embed_base_url: str | None
    embed_api_key: str | None
    embed_model: str | None
    embed_dim: int | None


@dataclass(frozen=True)
class ChatSettingsSnapshot:
    chat_base_url: str | None
    chat_api_key: str | None
    chat_model: str | None


@dataclass(frozen=True)
class LinkSettingsSnapshot:
    link_threshold_auto: float
    link_threshold_suggest: float


@dataclass(frozen=True)
class TrendSettingsSnapshot:
    chat_base_url: str | None
    chat_api_key: str | None
    chat_model: str | None
    trend_brand_prompt: str | None
    trend_base_url: str | None
    trend_api_key: str | None
    trend_model: str | None
    trend_source_config: str | None
    trend_score_threshold: float | None
    trend_result_limit: int | None
    trend_schedule_enabled: bool
    trend_schedule_frequency: str | None
    trend_schedule_mode: str | None
    trend_schedule_days_json: str | None
    trend_schedule_interval_hours: int | None
    trend_schedule_time: str | None
    trend_timezone: str | None
    trend_last_run_at: datetime | None
    trend_next_run_at: datetime | None


def snapshot_embedding_settings(settings: Settings) -> EmbeddingSettingsSnapshot:
    return EmbeddingSettingsSnapshot(
        embed_base_url=settings.embed_base_url,
        embed_api_key=settings.embed_api_key,
        embed_model=settings.embed_model,
        embed_dim=settings.embed_dim,
    )


def snapshot_chat_settings(settings: Settings) -> ChatSettingsSnapshot:
    return ChatSettingsSnapshot(
        chat_base_url=settings.chat_base_url,
        chat_api_key=settings.chat_api_key,
        chat_model=settings.chat_model,
    )


def snapshot_link_settings(settings: Settings) -> LinkSettingsSnapshot:
    return LinkSettingsSnapshot(
        link_threshold_auto=settings.link_threshold_auto,
        link_threshold_suggest=settings.link_threshold_suggest,
    )


def snapshot_trend_settings(settings: Settings) -> TrendSettingsSnapshot:
    return TrendSettingsSnapshot(
        chat_base_url=settings.chat_base_url,
        chat_api_key=settings.chat_api_key,
        chat_model=settings.chat_model,
        trend_brand_prompt=settings.trend_brand_prompt,
        trend_base_url=settings.trend_base_url,
        trend_api_key=settings.trend_api_key,
        trend_model=settings.trend_model,
        trend_source_config=settings.trend_source_config,
        trend_score_threshold=settings.trend_score_threshold,
        trend_result_limit=settings.trend_result_limit,
        trend_schedule_enabled=bool(settings.trend_schedule_enabled),
        trend_schedule_frequency=settings.trend_schedule_frequency,
        trend_schedule_mode=settings.trend_schedule_mode,
        trend_schedule_days_json=settings.trend_schedule_days_json,
        trend_schedule_interval_hours=settings.trend_schedule_interval_hours,
        trend_schedule_time=settings.trend_schedule_time,
        trend_timezone=settings.trend_timezone,
        trend_last_run_at=settings.trend_last_run_at,
        trend_next_run_at=settings.trend_next_run_at,
    )
