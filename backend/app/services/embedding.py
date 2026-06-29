"""Embedding 服务：向量生成、语义搜索。

vec_atoms 的建表/写入/KNN 操作委托给 app.vector_store 统一处理，
调用方无需感知底层是 sqlite-vec 还是 pgvector。
embed_dim 一旦写入 Settings 就锁定，切换 provider 需走 rebuild-embeddings 流程。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AtomEmbedding, Settings, ThoughtAtom
from ..vector_store import (
    get_vector,
    knn_search,
    serialize_vector,
    upsert_vector,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 防止 rebuild 和 embed_atom 同时操作 vec_atoms
_vec_table_lock = asyncio.Lock()


# ──────────────────────────────────────────────
# AI Provider 客户端
# ──────────────────────────────────────────────

def _get_client(settings: Settings) -> AsyncOpenAI:
    """根据 Settings 构造 OpenAI 兼容客户端，支持多家 provider。"""
    return AsyncOpenAI(
        api_key=settings.embed_api_key or "not-set",
        base_url=settings.embed_base_url or None,
    )


async def embed_texts(settings: Settings, texts: list[str]) -> list[list[float]]:
    """调用 embedding API，返回 float 向量列表。"""
    client = _get_client(settings)
    response = await client.embeddings.create(
        model=settings.embed_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def test_provider(settings: Settings) -> tuple[bool, float, str | None]:
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

async def embed_atom(session: Session, atom_id: str, settings: Settings) -> None:
    """为指定 atom 生成 embedding 并写入 vec_atoms 和 atom_embedding 元数据表。"""
    atom = session.get(ThoughtAtom, atom_id)
    if atom is None or atom.status == "deleted":
        logger.debug("atom %s 不存在或已删除，跳过 embed", atom_id)
        return

    vectors = await embed_texts(settings, [atom.content])
    vec = vectors[0]

    async with _vec_table_lock:
        upsert_vector(atom_id, vec)

    # 写入或更新 atom_embedding 元数据
    existing = session.get(AtomEmbedding, atom_id)
    if existing:
        existing.model_name = settings.embed_model
        existing.dim = settings.embed_dim
    else:
        session.add(AtomEmbedding(
            atom_id=atom_id,
            model_name=settings.embed_model,
            dim=settings.embed_dim,
        ))
    session.commit()
    logger.debug("atom %s embedding 已写入", atom_id)


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
    session: Session,
    query_text: str,
    settings: Settings,
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
