"""Settings 路由：AI provider 配置（Embedding / Chat 分离）、连通性测试、embedding 重建。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import DatabaseConnectionError, get_session, switch_database
from ..logger import get_logger
from ..models import AtomEmbedding, Settings, TaskQueue, ThoughtAtom
from ..runtime import start_background_worker, stop_background_worker
from ..services import task_queue as tq
from ..services.runtime_config import build_database_config, get_database_config
from ..services.embedding import atom_content_hash, embed_texts, test_provider
from ..services.chat import test_chat_provider
from ..services.settings_snapshot import snapshot_chat_settings, snapshot_embedding_settings, snapshot_trend_settings
from ..services.trend.collector import calculate_next_run_at, test_trend_provider
from ..services.trend.sources import normalize_source_config
from ..time_utils import utc_isoformat
from ..vector_store import create_vec_table, ensure_vec_table

logger = get_logger(__name__)
router = APIRouter()


class SettingsUpdate(BaseModel):
    embed_base_url: Optional[str] = None
    embed_api_key: Optional[str] = None   # 传空字符串 = 清除（embed_api_key 可为空）
    embed_model: Optional[str] = None
    embed_dim: Optional[int] = None
    chat_base_url: Optional[str] = None
    chat_api_key: Optional[str] = None    # 传空字符串 = 清除
    chat_model: Optional[str] = None
    link_threshold_auto: Optional[float] = None
    link_threshold_suggest: Optional[float] = None


class DatabaseSettingsOut(BaseModel):
    db_backend: str
    db_path: Optional[str]
    postgresql_url: Optional[str]
    restart_required: bool = False


class DatabaseSettingsUpdate(BaseModel):
    db_backend: str
    db_path: Optional[str] = None
    postgresql_url: Optional[str] = None

    @field_validator("db_backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        if value not in {"sqlite", "postgresql"}:
            raise ValueError("db_backend must be sqlite or postgresql")
        return value


class SettingsOut(BaseModel):
    embed_base_url: Optional[str]
    embed_api_key: Optional[str]
    embed_api_key_masked: Optional[str]   # 脱敏：仅展示后四位
    embed_model: Optional[str]
    embed_dim: Optional[int]
    embed_dim_locked: bool                # embed_dim / embed_model 已锁定（有 embedding 数据）
    embed_model_locked: bool
    chat_base_url: Optional[str]
    chat_api_key: Optional[str]
    chat_api_key_masked: Optional[str]    # 脱敏：仅展示后四位
    chat_model: Optional[str]
    link_threshold_auto: float
    link_threshold_suggest: float


class TrendSettingsUpdate(BaseModel):
    brand_prompt: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    reddit_enabled: Optional[bool] = None
    github_enabled: Optional[bool] = None
    hackernews_enabled: Optional[bool] = None
    google_enabled: Optional[bool] = None
    reddit_limit: Optional[int] = None
    github_limit: Optional[int] = None
    hackernews_limit: Optional[int] = None
    google_limit: Optional[int] = None
    github_token: Optional[str] = None
    score_threshold: Optional[float] = None
    result_limit: Optional[int] = None
    schedule_enabled: Optional[bool] = None
    schedule_frequency: Optional[str] = None
    schedule_mode: Optional[str] = None
    schedule_days: Optional[list[int]] = None
    schedule_interval_hours: Optional[int] = None
    schedule_time: Optional[str] = None


class TrendSettingsOut(BaseModel):
    brand_prompt: str
    llm_base_url: Optional[str]
    llm_api_key: Optional[str]
    llm_api_key_masked: Optional[str]
    llm_model: Optional[str]
    effective_llm_base_url: Optional[str]
    effective_llm_model: Optional[str]
    uses_chat_fallback: bool
    reddit_enabled: bool
    github_enabled: bool
    hackernews_enabled: bool
    google_enabled: bool
    reddit_limit: int
    github_limit: int
    hackernews_limit: int
    google_limit: int
    github_token: Optional[str]
    github_token_masked: Optional[str]
    score_threshold: float
    result_limit: int
    schedule_enabled: bool
    schedule_frequency: str
    schedule_mode: str
    schedule_days: list[int]
    schedule_interval_hours: int
    schedule_time: str
    last_run_at: Optional[str]
    next_run_at: Optional[str]


class TestProviderResult(BaseModel):
    ok: bool
    latency_ms: float
    error: Optional[str] = None


class EmbeddingStatusOut(BaseModel):
    active_atoms: int
    embedded_atoms: int
    stale_atoms: int
    pending: int
    running: int
    failed: int
    last_error: Optional[str] = None


class RetryFailedResult(BaseModel):
    retried: int


def _mask_key(key: str | None) -> str | None:
    """API key 脱敏：保留后四位，其余替换为 ***。"""
    if not key:
        return None
    if len(key) <= 4:
        return "****"
    return f"***{key[-4:]}"


def _get_or_create_settings(session: Session) -> Settings:
    """获取或创建单例 settings（id=1）。"""
    s = session.get(Settings, 1)
    if s is None:
        s = Settings(id=1)
        session.add(s)
        session.commit()
        session.refresh(s)
    return s


def _is_embed_dim_locked(session: Session) -> bool:
    """判断 embed_dim 是否已锁定：存在 atom_embedding 记录即视为锁定。"""
    return session.query(AtomEmbedding).first() is not None


def _to_out(s: Settings, session: Session) -> SettingsOut:
    locked = _is_embed_dim_locked(session)
    return SettingsOut(
        embed_base_url=s.embed_base_url,
        embed_api_key=s.embed_api_key,
        embed_api_key_masked=_mask_key(s.embed_api_key),
        embed_model=s.embed_model,
        embed_dim=s.embed_dim,
        embed_dim_locked=locked,
        embed_model_locked=locked,
        chat_base_url=s.chat_base_url,
        chat_api_key=s.chat_api_key,
        chat_api_key_masked=_mask_key(s.chat_api_key),
        chat_model=s.chat_model,
        link_threshold_auto=s.link_threshold_auto,
        link_threshold_suggest=s.link_threshold_suggest,
    )


def _source_config(s: Settings) -> dict:
    try:
        raw = json.loads(s.trend_source_config or "{}")
    except json.JSONDecodeError:
        raw = {}
    return normalize_source_config(raw)


def _write_source_config(s: Settings, config: dict) -> None:
    s.trend_source_config = json.dumps(normalize_source_config(config), ensure_ascii=False)


def _schedule_days(s: Settings) -> list[int]:
    try:
        raw = json.loads(s.trend_schedule_days_json or "[]")
    except json.JSONDecodeError:
        raw = []
    if not isinstance(raw, list):
        raw = []
    days = sorted({day for day in raw if isinstance(day, int) and 1 <= day <= 7})
    return days or [1, 2, 3, 4, 5, 6, 7]


def _write_schedule_days(s: Settings, days: list[int] | None) -> None:
    if days is None:
        return
    valid = sorted({day for day in days if isinstance(day, int) and 1 <= day <= 7})
    s.trend_schedule_days_json = json.dumps(valid or [1, 2, 3, 4, 5, 6, 7])


def _to_trend_out(s: Settings) -> TrendSettingsOut:
    source_config = _source_config(s)
    effective_base_url = s.trend_base_url or s.chat_base_url
    effective_model = s.trend_model or s.chat_model
    return TrendSettingsOut(
        brand_prompt=s.trend_brand_prompt or "",
        llm_base_url=s.trend_base_url,
        llm_api_key=s.trend_api_key,
        llm_api_key_masked=_mask_key(s.trend_api_key),
        llm_model=s.trend_model,
        effective_llm_base_url=effective_base_url,
        effective_llm_model=effective_model,
        uses_chat_fallback=not bool(s.trend_base_url or s.trend_api_key or s.trend_model),
        reddit_enabled=bool(source_config["reddit"]["enabled"]),
        github_enabled=bool(source_config["github"]["enabled"]),
        hackernews_enabled=bool(source_config["hackernews"]["enabled"]),
        google_enabled=bool(source_config["google"]["enabled"]),
        reddit_limit=int(source_config["reddit"]["limit"]),
        github_limit=int(source_config["github"]["limit"]),
        hackernews_limit=int(source_config["hackernews"]["limit"]),
        google_limit=int(source_config["google"]["limit"]),
        github_token=source_config["github"].get("token"),
        github_token_masked=_mask_key(source_config["github"].get("token")),
        score_threshold=s.trend_score_threshold if s.trend_score_threshold is not None else 70,
        result_limit=s.trend_result_limit if s.trend_result_limit is not None else 20,
        schedule_enabled=bool(s.trend_schedule_enabled),
        schedule_frequency=s.trend_schedule_frequency or "daily",
        schedule_mode=s.trend_schedule_mode or "weekly",
        schedule_days=_schedule_days(s),
        schedule_interval_hours=max(1, min(int(s.trend_schedule_interval_hours or 24), 24 * 30)),
        schedule_time=s.trend_schedule_time or "09:00",
        last_run_at=utc_isoformat(s.trend_last_run_at) if s.trend_last_run_at else None,
        next_run_at=utc_isoformat(s.trend_next_run_at) if s.trend_next_run_at else None,
    )


def _enqueue_link_discover_for_active_atoms(session: Session) -> int:
    atoms = (
        session.query(ThoughtAtom)
        .filter(ThoughtAtom.status != "deleted")
        .all()
    )
    for atom in atoms:
        tq.enqueue(session, "link_discover", {"atom_id": atom.id, "atom_version": atom.version})
    return len(atoms)


@router.get("", response_model=SettingsOut)
async def get_settings(session: Session = Depends(get_session)) -> SettingsOut:
    """获取当前 settings。单用户本地应用允许前端取回已保存的 API key。"""
    s = _get_or_create_settings(session)
    return _to_out(s, session)


@router.get("/trend", response_model=TrendSettingsOut)
async def get_trend_settings(session: Session = Depends(get_session)) -> TrendSettingsOut:
    """获取 Trend Settings。"""
    s = _get_or_create_settings(session)
    return _to_trend_out(s)


@router.put("/trend", response_model=TrendSettingsOut)
async def update_trend_settings(
    body: TrendSettingsUpdate,
    session: Session = Depends(get_session),
) -> TrendSettingsOut:
    """更新 Trend Settings。

    Trend LLM provider 为空时默认复用 Chat provider。
    """
    s = _get_or_create_settings(session)
    fields_set = body.model_fields_set
    source_config = _source_config(s)

    if "brand_prompt" in fields_set:
        s.trend_brand_prompt = body.brand_prompt or None
    if "llm_base_url" in fields_set:
        s.trend_base_url = body.llm_base_url or None
    if "llm_api_key" in fields_set:
        s.trend_api_key = body.llm_api_key or None
    if "llm_model" in fields_set:
        s.trend_model = body.llm_model or None

    source_fields = {
        "reddit_enabled",
        "github_enabled",
        "hackernews_enabled",
        "google_enabled",
        "reddit_limit",
        "github_limit",
        "hackernews_limit",
        "google_limit",
        "github_token",
    }
    if fields_set & source_fields:
        for key, source_name in [
            ("reddit_enabled", "reddit"),
            ("github_enabled", "github"),
            ("hackernews_enabled", "hackernews"),
            ("google_enabled", "google"),
        ]:
            if key in fields_set:
                source_config[source_name]["enabled"] = bool(getattr(body, key))
        for key, source_name in [
            ("reddit_limit", "reddit"),
            ("github_limit", "github"),
            ("hackernews_limit", "hackernews"),
            ("google_limit", "google"),
        ]:
            if key in fields_set and getattr(body, key) is not None:
                source_config[source_name]["limit"] = getattr(body, key)
        if "github_token" in fields_set:
            source_config["github"]["token"] = body.github_token or None
        _write_source_config(s, source_config)

    if "score_threshold" in fields_set and body.score_threshold is not None:
        s.trend_score_threshold = max(0, min(body.score_threshold, 100))
    if "result_limit" in fields_set and body.result_limit is not None:
        s.trend_result_limit = max(1, min(body.result_limit, 100))
    if "schedule_enabled" in fields_set and body.schedule_enabled is not None:
        s.trend_schedule_enabled = body.schedule_enabled
    if "schedule_frequency" in fields_set and body.schedule_frequency:
        if body.schedule_frequency not in {"hourly", "daily", "weekly"}:
            raise HTTPException(status_code=400, detail="schedule_frequency must be hourly, daily, or weekly")
        s.trend_schedule_frequency = body.schedule_frequency
    if "schedule_mode" in fields_set and body.schedule_mode:
        if body.schedule_mode not in {"weekly", "interval"}:
            raise HTTPException(status_code=400, detail="schedule_mode must be weekly or interval")
        s.trend_schedule_mode = body.schedule_mode
    if "schedule_days" in fields_set:
        _write_schedule_days(s, body.schedule_days)
    if "schedule_interval_hours" in fields_set and body.schedule_interval_hours is not None:
        s.trend_schedule_interval_hours = max(1, min(body.schedule_interval_hours, 24 * 30))
    if "schedule_time" in fields_set and body.schedule_time:
        s.trend_schedule_time = body.schedule_time

    if fields_set & {
        "schedule_enabled",
        "schedule_frequency",
        "schedule_mode",
        "schedule_days",
        "schedule_interval_hours",
        "schedule_time",
    }:
        s.trend_next_run_at = calculate_next_run_at(s) if s.trend_schedule_enabled else None

    session.commit()
    session.refresh(s)
    return _to_trend_out(s)


@router.get("/database", response_model=DatabaseSettingsOut)
async def get_database_settings() -> DatabaseSettingsOut:
    """获取数据库后端配置。此接口不依赖数据库连接。"""
    return DatabaseSettingsOut(**get_database_config())


@router.put("/database", response_model=DatabaseSettingsOut)
async def update_database_settings(body: DatabaseSettingsUpdate) -> DatabaseSettingsOut:
    """热切换业务数据库。

    这里不做数据迁移；目标库只会被升级到当前 schema。
    """
    db_path = (body.db_path or "").strip()
    postgresql_url = (body.postgresql_url or "").strip()

    if body.db_backend == "sqlite" and not db_path:
        raise HTTPException(status_code=400, detail="选择 SQLite 时必须提供数据库文件路径")
    if body.db_backend == "postgresql":
        if not postgresql_url:
            raise HTTPException(status_code=400, detail="选择 PostgreSQL 时必须提供连接 URL")
        if not (
            postgresql_url.startswith("postgresql://")
            or postgresql_url.startswith("postgresql+psycopg2://")
        ):
            raise HTTPException(
                status_code=400,
                detail="PostgreSQL URL 必须以 postgresql:// 或 postgresql+psycopg2:// 开头",
            )

    target = build_database_config(
        body.db_backend,
        db_path or None,
        postgresql_url or None,
    )

    await stop_background_worker()
    try:
        switched = switch_database(target)
    except DatabaseConnectionError as exc:
        await start_background_worker()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await start_background_worker()
        raise HTTPException(status_code=500, detail=f"数据库切换失败：{exc}") from exc
    await start_background_worker()

    return DatabaseSettingsOut(
        db_backend=switched.db_backend,
        db_path=switched.db_path,
        postgresql_url=switched.postgresql_url,
        restart_required=False,
    )


@router.put("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    session: Session = Depends(get_session),
) -> SettingsOut:
    """更新 settings。embed_dim 已锁定时变更需先调用 rebuild-embeddings。"""
    s = _get_or_create_settings(session)
    fields_set = body.model_fields_set
    locked = _is_embed_dim_locked(session)

    # embed_dim / embed_model 锁定校验
    if "embed_dim" in fields_set and body.embed_dim is not None and body.embed_dim != s.embed_dim:
        if locked:
            raise HTTPException(
                status_code=400,
                detail="embed_dim 已锁定，切换维度请先调用 POST /api/settings/rebuild-embeddings",
            )
        # 首次设置 embed_dim，建表
        ensure_vec_table(body.embed_dim)

    if "embed_model" in fields_set and body.embed_model and body.embed_model != s.embed_model:
        if locked:
            raise HTTPException(
                status_code=400,
                detail="embed_model 已锁定，切换模型请先调用 POST /api/settings/rebuild-embeddings",
            )
    if "embed_base_url" in fields_set:
        s.embed_base_url = body.embed_base_url or None
    if "embed_api_key" in fields_set:
        s.embed_api_key = body.embed_api_key or None
    if "embed_model" in fields_set:
        s.embed_model = body.embed_model or None
    if "embed_dim" in fields_set and body.embed_dim is not None:
        s.embed_dim = body.embed_dim
    if "chat_base_url" in fields_set:
        s.chat_base_url = body.chat_base_url or None
    if "chat_api_key" in fields_set:
        s.chat_api_key = body.chat_api_key or None
    if "chat_model" in fields_set:
        s.chat_model = body.chat_model or None
    if "link_threshold_auto" in fields_set and body.link_threshold_auto is not None:
        s.link_threshold_auto = body.link_threshold_auto
    if "link_threshold_suggest" in fields_set and body.link_threshold_suggest is not None:
        s.link_threshold_suggest = body.link_threshold_suggest

    session.commit()
    session.refresh(s)
    if (
        ("link_threshold_auto" in fields_set and body.link_threshold_auto is not None)
        or ("link_threshold_suggest" in fields_set and body.link_threshold_suggest is not None)
    ):
        queued = _enqueue_link_discover_for_active_atoms(session)
        logger.info("关联阈值已更新，已入队 link_discover %d 条", queued)
    logger.info("settings 已更新")
    return _to_out(s, session)


@router.post("/test-provider", response_model=TestProviderResult)
async def test_provider_endpoint(
    session: Session = Depends(get_session),
) -> TestProviderResult:
    """测试 Embedding provider 连通性（发送一条 embedding 请求并计时）。"""
    s = _get_or_create_settings(session)
    if not s.embed_model:
        raise HTTPException(status_code=400, detail="请先配置 embed_model")

    settings_snapshot = snapshot_embedding_settings(s)
    session.close()
    ok, latency_ms, error = await test_provider(settings_snapshot)
    if ok:
        logger.info("embedding provider 测试成功 latency=%.1fms", latency_ms)
    else:
        logger.warning("embedding provider 测试失败: %s", error)
    return TestProviderResult(ok=ok, latency_ms=latency_ms, error=error)


@router.post("/test-chat-provider", response_model=TestProviderResult)
async def test_chat_provider_endpoint(
    session: Session = Depends(get_session),
) -> TestProviderResult:
    """测试 Chat provider 连通性（发送一条 chat 请求并计时）。"""
    s = _get_or_create_settings(session)
    if not s.chat_model:
        raise HTTPException(status_code=400, detail="请先配置 chat_model")

    settings_snapshot = snapshot_chat_settings(s)
    session.close()
    ok, latency_ms, error = await test_chat_provider(settings_snapshot)
    if ok:
        logger.info("chat provider 测试成功 latency=%.1fms", latency_ms)
    else:
        logger.warning("chat provider 测试失败: %s", error)
    return TestProviderResult(ok=ok, latency_ms=latency_ms, error=error)


@router.post("/test-trend-provider", response_model=TestProviderResult)
async def test_trend_provider_endpoint(
    session: Session = Depends(get_session),
) -> TestProviderResult:
    """测试 Trend LLM provider；未单独配置时复用 Chat provider。"""
    s = _get_or_create_settings(session)
    settings_snapshot = snapshot_trend_settings(s)
    session.close()
    ok, latency_ms, error = await test_trend_provider(settings_snapshot)
    if ok:
        logger.info("trend provider 测试成功 latency=%.1fms", latency_ms)
    else:
        logger.warning("trend provider 测试失败: %s", error)
    return TestProviderResult(ok=ok, latency_ms=latency_ms, error=error)


@router.get("/embedding-status", response_model=EmbeddingStatusOut)
async def get_embedding_status(session: Session = Depends(get_session)) -> EmbeddingStatusOut:
    """获取 embedding 同步状态，用于设置页展示真实队列进度。"""
    active_atoms = (
        session.query(ThoughtAtom)
        .filter(ThoughtAtom.status != "deleted")
        .all()
    )
    active_ids = {atom.id for atom in active_atoms}
    embeddings = {
        embedding.atom_id: embedding
        for embedding in session.query(AtomEmbedding)
        .filter(AtomEmbedding.atom_id.in_(active_ids))
        .all()
    } if active_ids else {}

    embedded_atoms = 0
    stale_atoms = 0
    for atom in active_atoms:
        embedding = embeddings.get(atom.id)
        if (
            embedding
            and embedding.atom_version == atom.version
            and embedding.content_hash == atom_content_hash(atom.content)
        ):
            embedded_atoms += 1
        else:
            stale_atoms += 1

    task_counts = {
        status: count
        for status, count in (
            session.query(TaskQueue.status, func.count(TaskQueue.id))
            .filter(TaskQueue.task_type == "embed")
            .group_by(TaskQueue.status)
            .all()
        )
    }
    last_failed = (
        session.query(TaskQueue)
        .filter(TaskQueue.task_type == "embed")
        .filter(TaskQueue.last_error.is_not(None))
        .order_by(TaskQueue.updated_at.desc())
        .first()
    )
    last_embedding_error = (
        session.query(AtomEmbedding)
        .filter(AtomEmbedding.last_error.is_not(None))
        .order_by(AtomEmbedding.updated_at.desc())
        .first()
    )
    return EmbeddingStatusOut(
        active_atoms=len(active_atoms),
        embedded_atoms=embedded_atoms,
        stale_atoms=stale_atoms,
        pending=task_counts.get("pending", 0),
        running=task_counts.get("running", 0),
        failed=task_counts.get("failed", 0),
        last_error=(
            last_failed.last_error
            if last_failed and last_failed.last_error
            else last_embedding_error.last_error if last_embedding_error else None
        ),
    )


@router.post("/retry-failed-embeddings", response_model=RetryFailedResult)
async def retry_failed_embeddings(session: Session = Depends(get_session)) -> RetryFailedResult:
    """重试失败的 embedding 任务。"""
    retried = tq.retry_failed(session, "embed")
    logger.info("已重试 failed embedding 任务 %d 条", retried)
    return RetryFailedResult(retried=retried)


@router.post("/rebuild-embeddings")
async def rebuild_embeddings(
    body: SettingsUpdate = SettingsUpdate(),
    session: Session = Depends(get_session),
) -> dict:
    """重建所有 embedding：drop + recreate vec_atoms，批量入队 embed 任务。

    用于切换 embedding provider 或 embed_dim 变更后的全量重建。
    """
    s = _get_or_create_settings(session)
    await stop_background_worker()

    try:
        # 如果请求体包含新 embed_dim，先更新
        new_dim = body.embed_dim if body.embed_dim is not None else s.embed_dim
        if not new_dim:
            raise HTTPException(status_code=400, detail="请先配置 embed_dim")

        # 应用其他 settings 更新
        if body.embed_base_url is not None:
            s.embed_base_url = body.embed_base_url or None
        if body.embed_api_key is not None:
            s.embed_api_key = body.embed_api_key or None
        if body.embed_model is not None:
            s.embed_model = body.embed_model or None
        if body.embed_dim is not None:
            s.embed_dim = body.embed_dim
        session.commit()
        session.refresh(s)
        settings_snapshot = snapshot_embedding_settings(s)
        session.close()

        # 以 provider 实际返回维度为准，避免用户选错维度后重建出不可写入的 vec_atoms。
        try:
            probe_vectors = await embed_texts(settings_snapshot, ["sparkling embedding dimension probe"])
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Embedding provider 测试失败：{exc}") from exc
        actual_dim = len(probe_vectors[0])
        if actual_dim <= 0:
            raise HTTPException(status_code=400, detail="Embedding provider 返回了空向量")
        if actual_dim != new_dim:
            raise HTTPException(
                status_code=400,
                detail=f"Embed Dim 不匹配：配置为 {new_dim}，但 provider 返回了 {actual_dim} 维。请重新选择正确的维度。",
            )

        # 强制重建 vec_atoms 虚表
        create_vec_table(new_dim)

        # 清空 atom_embedding 元数据和旧的重建任务；worker 已暂停，可安全清理 running。
        session.query(AtomEmbedding).delete()
        (
            session.query(TaskQueue)
            .filter(TaskQueue.task_type.in_(["embed", "link_discover"]))
            .filter(TaskQueue.status.in_(["pending", "running", "failed"]))
            .delete(synchronize_session=False)
        )
        session.commit()

        # 为所有未删除的 atom 入队 embed 任务
        atoms = (
            session.query(ThoughtAtom)
            .filter(ThoughtAtom.status != "deleted")
            .all()
        )
        for atom in atoms:
            tq.enqueue(session, "embed", {"atom_id": atom.id, "atom_version": atom.version})

        logger.info("embedding 重建已入队 %d 条，dim=%s", len(atoms), new_dim)
        return {"queued": len(atoms), "embed_dim": new_dim}
    finally:
        await start_background_worker()
