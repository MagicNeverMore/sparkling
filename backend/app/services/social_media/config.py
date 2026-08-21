"""固定 control SQLite 中的 Social Media Settings。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...logger import get_logger
from ..settings.runtime_config import connect_control_db

logger = get_logger(__name__)


@dataclass(frozen=True)
class SocialMediaConfig:
    schedule_enabled: bool
    update_frequency: str
    schedule_time: str
    timezone: str
    youtube_client_id: str | None
    youtube_client_secret: str | None
    youtube_refresh_token: str | None
    youtube_channel_id: str | None
    youtube_channel_title: str | None
    oauth_state: str | None
    oauth_redirect_uri: str | None
    last_run_at: str | None
    next_run_at: str | None

    @property
    def youtube_connected(self) -> bool:
        return bool(self.youtube_refresh_token and self.youtube_channel_id)


_FIELDS = (
    "schedule_enabled, update_frequency, schedule_time, timezone, "
    "youtube_client_id, youtube_client_secret, youtube_refresh_token, "
    "youtube_channel_id, youtube_channel_title, "
    "oauth_state, oauth_redirect_uri, last_run_at, next_run_at"
)


def load_social_media_config() -> SocialMediaConfig:
    with connect_control_db() as conn:
        row = conn.execute(f"SELECT {_FIELDS} FROM social_media_config WHERE id = 1").fetchone()  # noqa: S608
    if row is None:
        raise RuntimeError("Social Media Settings 未初始化")
    config = SocialMediaConfig(
        schedule_enabled=bool(row["schedule_enabled"]),
        update_frequency=row["update_frequency"],
        schedule_time=row["schedule_time"],
        timezone=row["timezone"],
        youtube_client_id=row["youtube_client_id"],
        youtube_client_secret=row["youtube_client_secret"],
        youtube_refresh_token=row["youtube_refresh_token"],
        youtube_channel_id=row["youtube_channel_id"],
        youtube_channel_title=row["youtube_channel_title"],
        oauth_state=row["oauth_state"],
        oauth_redirect_uri=row["oauth_redirect_uri"],
        last_run_at=row["last_run_at"],
        next_run_at=row["next_run_at"],
    )
    logger.debug(
        "social_media.config.loaded youtube_connected=%s refresh_credential_present=%s "
        "has_channel_id=%s channel_id=%s",
        config.youtube_connected,
        bool(config.youtube_refresh_token),
        bool(config.youtube_channel_id),
        config.youtube_channel_id,
    )
    return config


def update_social_media_config(**fields: object) -> SocialMediaConfig:
    allowed = {
        "schedule_enabled",
        "update_frequency",
        "schedule_time",
        "timezone",
        "youtube_client_id",
        "youtube_client_secret",
        "youtube_refresh_token",
        "youtube_channel_id",
        "youtube_channel_title",
        "oauth_state",
        "oauth_redirect_uri",
        "last_run_at",
        "next_run_at",
    }
    invalid = set(fields) - allowed
    if invalid:
        raise ValueError(f"未知 Social Media Settings 字段: {', '.join(sorted(invalid))}")
    if not fields:
        return load_social_media_config()
    normalized = {
        key: int(value) if key == "schedule_enabled" and value is not None else value
        for key, value in fields.items()
    }
    normalized["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    assignments = ", ".join(f"{key} = ?" for key in normalized)
    with connect_control_db() as conn:
        cursor = conn.execute(
            f"UPDATE social_media_config SET {assignments} WHERE id = 1",  # noqa: S608
            tuple(normalized.values()),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            logger.error(
                "social_media.config.update_failed reason=row_not_found fields=%s",
                sorted(fields),
            )
            raise RuntimeError("Social Media Settings 持久化失败：配置记录不存在")
        conn.commit()
    saved = load_social_media_config()
    logger.info(
        "social_media.config.updated fields=%s youtube_connected=%s "
        "refresh_credential_present=%s has_channel_id=%s channel_id=%s",
        sorted(fields),
        saved.youtube_connected,
        bool(saved.youtube_refresh_token),
        bool(saved.youtube_channel_id),
        saved.youtube_channel_id,
    )
    return saved


def disconnect_youtube() -> SocialMediaConfig:
    return update_social_media_config(
        youtube_refresh_token=None,
        youtube_channel_id=None,
        youtube_channel_title=None,
        oauth_state=None,
        oauth_redirect_uri=None,
        last_run_at=None,
        next_run_at=None,
    )
