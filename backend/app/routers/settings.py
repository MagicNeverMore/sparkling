"""Settings 路由：AI provider 配置、连通性测试、embedding 重建。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import AtomEmbedding, Settings, ThoughtAtom
from ..services import task_queue as tq
from ..services.embedding import create_vec_table, ensure_vec_table, test_provider

router = APIRouter()


class SettingsUpdate(BaseModel):
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None      # 传空字符串 = 清除
    embed_model: Optional[str] = None
    embed_dim: Optional[int] = None
    chat_model: Optional[str] = None
    link_threshold_auto: Optional[float] = None
    link_threshold_suggest: Optional[float] = None


class SettingsOut(BaseModel):
    ai_base_url: Optional[str]
    ai_api_key_masked: Optional[str]       # 脱敏：仅展示后四位
    embed_model: Optional[str]
    embed_dim: Optional[int]
    embed_dim_locked: bool                 # embed_dim 已锁定（有 embedding 数据）
    chat_model: Optional[str]
    link_threshold_auto: float
    link_threshold_suggest: float


class TestProviderResult(BaseModel):
    ok: bool
    latency_ms: float
    error: Optional[str] = None


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
    return SettingsOut(
        ai_base_url=s.ai_base_url,
        ai_api_key_masked=_mask_key(s.ai_api_key),
        embed_model=s.embed_model,
        embed_dim=s.embed_dim,
        embed_dim_locked=_is_embed_dim_locked(session),
        chat_model=s.chat_model,
        link_threshold_auto=s.link_threshold_auto,
        link_threshold_suggest=s.link_threshold_suggest,
    )


@router.get("", response_model=SettingsOut)
async def get_settings(session: Session = Depends(get_session)) -> SettingsOut:
    """获取当前 settings，api_key 脱敏返回。"""
    s = _get_or_create_settings(session)
    return _to_out(s, session)


@router.put("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    session: Session = Depends(get_session),
) -> SettingsOut:
    """更新 settings。embed_dim 已锁定时变更需先调用 rebuild-embeddings。"""
    s = _get_or_create_settings(session)

    # embed_dim 锁定校验
    if body.embed_dim is not None and body.embed_dim != s.embed_dim:
        if _is_embed_dim_locked(session):
            raise HTTPException(
                status_code=400,
                detail="embed_dim 已锁定，切换维度请先调用 POST /api/settings/rebuild-embeddings",
            )
        # 首次设置 embed_dim，建表
        ensure_vec_table(body.embed_dim)

    if body.ai_base_url is not None:
        s.ai_base_url = body.ai_base_url or None
    if body.ai_api_key is not None:
        s.ai_api_key = body.ai_api_key or None
    if body.embed_model is not None:
        s.embed_model = body.embed_model or None
    if body.embed_dim is not None:
        s.embed_dim = body.embed_dim
    if body.chat_model is not None:
        s.chat_model = body.chat_model or None
    if body.link_threshold_auto is not None:
        s.link_threshold_auto = body.link_threshold_auto
    if body.link_threshold_suggest is not None:
        s.link_threshold_suggest = body.link_threshold_suggest

    session.commit()
    session.refresh(s)
    return _to_out(s, session)


@router.post("/test-provider", response_model=TestProviderResult)
async def test_provider_endpoint(
    session: Session = Depends(get_session),
) -> TestProviderResult:
    """测试当前 AI provider 连通性（发送一条 embedding 请求并计时）。"""
    s = _get_or_create_settings(session)
    if not s.embed_model:
        raise HTTPException(status_code=400, detail="请先配置 embed_model")

    ok, latency_ms, error = await test_provider(s)
    return TestProviderResult(ok=ok, latency_ms=latency_ms, error=error)


@router.post("/rebuild-embeddings")
async def rebuild_embeddings(
    body: SettingsUpdate = SettingsUpdate(),
    session: Session = Depends(get_session),
) -> dict:
    """重建所有 embedding：drop + recreate vec_atoms，批量入队 embed 任务。

    用于切换 embedding provider 或 embed_dim 变更后的全量重建。
    """
    s = _get_or_create_settings(session)

    # 如果请求体包含新 embed_dim，先更新
    new_dim = body.embed_dim if body.embed_dim is not None else s.embed_dim
    if not new_dim:
        raise HTTPException(status_code=400, detail="请先配置 embed_dim")

    # 应用其他 settings 更新
    if body.ai_base_url is not None:
        s.ai_base_url = body.ai_base_url or None
    if body.ai_api_key is not None:
        s.ai_api_key = body.ai_api_key or None
    if body.embed_model is not None:
        s.embed_model = body.embed_model or None
    if body.embed_dim is not None:
        s.embed_dim = body.embed_dim
    session.commit()

    # 强制重建 vec_atoms 虚表
    create_vec_table(new_dim)

    # 清空 atom_embedding 元数据
    session.query(AtomEmbedding).delete()
    session.commit()

    # 为所有未删除的 atom 入队 embed 任务
    atoms = (
        session.query(ThoughtAtom)
        .filter(ThoughtAtom.status != "deleted")
        .all()
    )
    for atom in atoms:
        tq.enqueue(session, "embed", {"atom_id": atom.id})

    return {"queued": len(atoms), "embed_dim": new_dim}
