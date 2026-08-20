"""部署级运行时配置：保存在固定 control SQLite，不随业务数据库切换。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from ...logger import get_logger
from .runtime_config import connect_control_db

logger = get_logger(__name__)


@dataclass(frozen=True)
class DeploymentConfig:
    public_origin: str | None


def normalize_public_origin(value: str | None) -> str | None:
    """规范化公开 origin；生产域名必须使用 HTTPS。"""
    if value is None or not value.strip():
        return None
    parsed = urlsplit(value.strip())
    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError("Public URL 的端口格式无效") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Public URL 只能包含协议、域名和可选端口")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and hostname not in local_hosts and not hostname.endswith(".localhost"):
        raise ValueError("生产环境 Public URL 必须使用 HTTPS")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def load_deployment_config() -> DeploymentConfig:
    with connect_control_db() as conn:
        row = conn.execute("SELECT public_origin FROM deployment_config WHERE id = 1").fetchone()
    return DeploymentConfig(public_origin=row["public_origin"] if row else None)


def save_public_origin(value: str | None) -> DeploymentConfig:
    """保存后立即生效；地址变化时废弃尚未完成的 OAuth 流程。"""
    public_origin = normalize_public_origin(value)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with connect_control_db() as conn:
        previous = conn.execute(
            "SELECT public_origin FROM deployment_config WHERE id = 1"
        ).fetchone()
        previous_origin = previous["public_origin"] if previous else None
        conn.execute(
            """
            INSERT INTO deployment_config (id, public_origin, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              public_origin = excluded.public_origin,
              updated_at = excluded.updated_at
            """,
            (public_origin, now),
        )
        if previous_origin != public_origin:
            conn.execute(
                """
                UPDATE social_media_config
                SET oauth_state = NULL, oauth_redirect_uri = NULL, updated_at = ?
                WHERE id = 1
                """,
                (now,),
            )
        conn.commit()
    logger.info(
        "deployment.public_origin.updated configured=%s changed=%s origin=%s",
        public_origin is not None,
        previous_origin != public_origin,
        public_origin,
    )
    return DeploymentConfig(public_origin=public_origin)
