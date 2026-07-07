"""Embedding 服务：向量生成、语义搜索。

vec_atoms 的建表/写入/KNN 操作委托给 app.vector_store 统一处理，
调用方无需感知底层是 sqlite-vec 还是 pgvector。
embed_dim 一旦写入 Settings 就锁定，切换 provider 需走 rebuild-embeddings 流程。
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import SessionLocal
from ...logger import get_logger
from ...models import AtomEmbedding, Settings, ThoughtAtom
from ..settings.settings_snapshot import EmbeddingSettingsSnapshot, snapshot_embedding_settings
from ..ai.openai_compat import normalize_base_url
from ...vector_store import (
    delete_vectors,
    get_vector,
    knn_search,
    serialize_vector,
    upsert_vector,
    vec_table_exists,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# 防止 rebuild 和 embed_atom 同时操作 vec_atoms
_vec_table_lock = asyncio.Lock()
EmbeddingSettings = Settings | EmbeddingSettingsSnapshot
MAX_EMBEDDING_TEXT_CHARS = 12_000


@dataclass(frozen=True)
class _EmbeddingWork:
    atom_id: str
    content: str
    version: int
    content_hash: str
    needs_embedding: bool = True


# ──────────────────────────────────────────────
# AI Provider 客户端
# ──────────────────────────────────────────────

def _get_client(settings: EmbeddingSettings) -> AsyncOpenAI:
    """根据 Settings 构造 OpenAI 兼容客户端，支持多家 provider。"""
    return AsyncOpenAI(
        api_key=settings.embed_api_key or "not-set",
        base_url=normalize_base_url(settings.embed_base_url),
    )


async def embed_texts(settings: EmbeddingSettings, texts: list[str]) -> list[list[float]]:
    """调用 embedding API，返回 float 向量列表。"""
    client = _get_client(settings)
    kwargs: dict = dict(
        model=cast(str, settings.embed_model),
        input=[prepare_embedding_text(text) for text in texts],
    )
    # 指定维度：OpenAI text-embedding-3-* 支持 dimensions 参数；
    # 不支持的 provider（如 Ollama 旧版）可能忽略或报错，需用户调整
    if settings.embed_dim:
        kwargs["dimensions"] = settings.embed_dim
    response = await client.embeddings.create(**kwargs)
    return [item.embedding for item in response.data]


def prepare_embedding_text(text: str) -> str:
    """限制 embedding 输入大小，避免超长内容拖垮 provider 或触发 token limit。"""
    value = (text or "").strip()
    if len(value) <= MAX_EMBEDDING_TEXT_CHARS:
        return value
    return value[:MAX_EMBEDDING_TEXT_CHARS]


async def test_provider(settings: EmbeddingSettings) -> tuple[bool, float, str | None]:
    """测试 AI provider 连通性，返回 (ok, latency_ms, error_msg)。"""
    start = time.monotonic()
    try:
        await embed_texts(settings, ["sparkling connectivity test"])
        latency = (time.monotonic() - start) * 1000
        return True, round(latency, 1), None
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return False, round(latency, 1), str(exc)


# ──────────────────────────────────────────────
# 核心业务：为单条 atom 生成并持久化 embedding
# ──────────────────────────────────────────────

async def embed_atom(session: Session, atom_id: str, settings: Settings) -> bool:
    """为指定 atom 生成 embedding 并写入 vec_atoms 和 atom_embedding 元数据表。"""
    return await sync_atom_embedding(
        atom_id,
        snapshot_embedding_settings(settings),
    )


async def sync_atom_embedding(
    atom_id: str,
    settings: EmbeddingSettings,
    expected_version: int | None = None,
) -> bool:
    """同步单条 atom 的 embedding。

    返回 True 表示本次确认 vector store 已包含当前内容；返回 False 表示任务已过期或 atom 已删除。
    """
    work = _load_embedding_work(atom_id, expected_version)
    if work is None:
        return False
    if not work.needs_embedding:
        return True

    vectors = await embed_texts(settings, [work.content])
    vec = vectors[0]

    async with _vec_table_lock:
        with SessionLocal() as session:
            atom = session.get(ThoughtAtom, atom_id)
            if (
                atom is None
                or atom.status == "deleted"
                or atom.version != work.version
                or atom_content_hash(atom.content) != work.content_hash
            ):
                logger.info("atom %s embed 写入前已变化，跳过旧任务", atom_id)
                return False

            existing = session.get(AtomEmbedding, atom_id)
            if (
                existing
                and existing.atom_version == work.version
                and existing.content_hash == work.content_hash
                and get_vector(atom_id) is not None
            ):
                logger.debug("atom %s embedding 已是最新，跳过重算", atom_id)
                return True

            upsert_vector(atom_id, vec)

            if existing:
                existing.model_name = settings.embed_model
                existing.dim = settings.embed_dim
                existing.atom_version = work.version
                existing.content_hash = work.content_hash
                existing.last_error = None
            else:
                session.add(AtomEmbedding(
                    atom_id=atom_id,
                    model_name=settings.embed_model,
                    dim=settings.embed_dim,
                    atom_version=work.version,
                    content_hash=work.content_hash,
                ))
            session.commit()
    logger.debug("atom %s embedding 已写入", atom_id)
    return True


def _load_embedding_work(atom_id: str, expected_version: int | None) -> _EmbeddingWork | None:
    with SessionLocal() as session:
        atom = session.get(ThoughtAtom, atom_id)
        if atom is None or atom.status == "deleted":
            logger.debug("atom %s 不存在或已删除，跳过 embed", atom_id)
            return None

        if expected_version is not None and expected_version != atom.version:
            logger.info(
                "atom %s embed 任务版本过期，payload=%s current=%s",
                atom_id,
                expected_version,
                atom.version,
            )
            return None

        content_hash = atom_content_hash(atom.content)
        existing = session.get(AtomEmbedding, atom_id)
        if (
            existing
            and existing.atom_version == atom.version
            and existing.content_hash == content_hash
            and get_vector(atom_id) is not None
        ):
            logger.debug("atom %s embedding 已是最新，跳过重算", atom_id)
            return _EmbeddingWork(
                atom_id=atom_id,
                content=atom.content,
                version=atom.version,
                content_hash=content_hash,
                needs_embedding=False,
            )

        return _EmbeddingWork(
            atom_id=atom_id,
            content=atom.content,
            version=atom.version,
            content_hash=content_hash,
        )


def delete_atom_embedding(session: Session, atom_id: str) -> None:
    """从 vector store 和 atom_embedding 元数据表移除指定 atom 的 embedding。"""
    if vec_table_exists():
        delete_vectors([atom_id])
    existing = session.get(AtomEmbedding, atom_id)
    if existing:
        session.delete(existing)
        session.commit()


def mark_atom_embedding_error(session: Session, atom_id: str, error: str) -> None:
    """记录指定 atom 最近一次 embedding 错误，便于设置页展示。"""
    existing = session.get(AtomEmbedding, atom_id)
    if not existing:
        return
    existing.last_error = error[:2000]
    session.commit()


def atom_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────
# KNN 查询（用已存向量，不重新 embed）
# ──────────────────────────────────────────────

def knn_by_existing_embedding(
    atom_id: str,
    k: int,
    exclude_deleted_ids: set[str] | None = None,
) -> list[tuple[str, float]]:
    """从 vec_atoms 直接取 atom_id 的向量做 KNN，返回 (neighbor_id, similarity) 列表。

    similarity = 1 - cosine_distance，范围 [0, 1]，越高越相关。
    不重新调用 embedding API，适合 link_discover worker 使用。
    """
    embedding_bytes = get_vector(atom_id)
    if embedding_bytes is None:
        return []

    rows = knn_search(embedding_bytes, k, exclude_id=atom_id)

    deleted = exclude_deleted_ids or set()
    return [
        (r[0], round(1 - r[1], 6))
        for r in rows
        if r[0] not in deleted
    ]


# ──────────────────────────────────────────────
# 语义搜索（用户输入文本 → embed → KNN）
# ──────────────────────────────────────────────

async def search_similar(
    query_text: str,
    settings: EmbeddingSettings,
    k: int = 20,
) -> list[tuple[str, float]]:
    """语义搜索：embed 查询文本 → KNN → 返回 (atom_id, similarity) 列表。

    settings 未配置 embed_dim 时直接返回空列表，不抛异常。
    """
    if not settings.embed_dim or not settings.embed_model:
        return []

    vectors = await embed_texts(settings, [query_text])
    q_vec = vectors[0]

    # 查询已删除 atom 的 id，用于过滤结果
    with SessionLocal() as session:
        deleted_ids = {
            row[0]
            for row in session.execute(
                select(ThoughtAtom.id).where(ThoughtAtom.status == "deleted")
            ).fetchall()
        }

    # 序列化查询向量用于 KNN（vector_store 内部处理序列化）
    q_bytes = serialize_vector(q_vec)

    rows = knn_search(q_bytes, k)

    return [
        (r[0], round(1 - r[1], 6))
        for r in rows
        if r[0] not in deleted_ids
    ]
