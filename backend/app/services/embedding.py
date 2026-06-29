"""Embedding 服务：vec_table 管理、向量生成、语义搜索。

vec_atoms 是 sqlite-vec 虚表，不归 SQLAlchemy 管，动态建表。
embed_dim 一旦写入 Settings 就锁定，切换 provider 需走 rebuild-embeddings 流程。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import sqlite_vec
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_raw_conn
from ..models import AtomEmbedding, Settings, ThoughtAtom

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 防止 rebuild 和 embed_atom 同时操作 vec_atoms
_vec_table_lock = asyncio.Lock()


# ──────────────────────────────────────────────
# vec_atoms 虚表管理
# ──────────────────────────────────────────────

def ensure_vec_table(dim: int) -> None:
    """首次设置 embed_dim 时创建 vec_atoms 虚表（已存在则跳过）。"""
    with get_raw_conn() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_atoms'"
        ).fetchone()
        if exists:
            return
        _do_create_vec_table(conn, dim)
        logger.info("vec_atoms 虚表已创建，维度=%d", dim)


def create_vec_table(dim: int) -> None:
    """强制重建 vec_atoms（rebuild-embeddings 流程调用）。"""
    with get_raw_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS vec_atoms")
        _do_create_vec_table(conn, dim)
        logger.info("vec_atoms 虚表已重建，维度=%d", dim)


def _do_create_vec_table(conn, dim: int) -> None:
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_atoms "
        f"USING vec0(atom_id TEXT PRIMARY KEY, embedding float[{dim}] distance_metric=cosine)"
    )
    conn.commit()


# ──────────────────────────────────────────────
# AI Provider 客户端
# ──────────────────────────────────────────────

def _get_client(settings: Settings) -> AsyncOpenAI:
    """根据 Settings 构造 OpenAI 兼容客户端，支持多家 provider。"""
    return AsyncOpenAI(
        api_key=settings.ai_api_key or "not-set",
        base_url=settings.ai_base_url or None,
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
    vec_bytes = sqlite_vec.serialize_float32(vec)

    async with _vec_table_lock:
        with get_raw_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO vec_atoms(atom_id, embedding) VALUES (?, ?)",
                [atom_id, vec_bytes],
            )
            conn.commit()

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
    with get_raw_conn() as conn:
        row = conn.execute(
            "SELECT embedding FROM vec_atoms WHERE atom_id = ?", [atom_id]
        ).fetchone()
        if row is None:
            return []
        embedding_bytes = row[0]
        rows = conn.execute(
            "SELECT atom_id, distance FROM vec_atoms "
            "WHERE embedding MATCH ? AND k = ? AND atom_id != ?",
            [embedding_bytes, k, atom_id],
        ).fetchall()

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
    q_bytes = sqlite_vec.serialize_float32(vectors[0])

    # 查询已删除 atom 的 id，用于过滤结果
    deleted_ids = {
        row[0]
        for row in session.execute(
            select(ThoughtAtom.id).where(ThoughtAtom.status == "deleted")
        ).fetchall()
    }

    with get_raw_conn() as conn:
        rows = conn.execute(
            "SELECT atom_id, distance FROM vec_atoms WHERE embedding MATCH ? AND k = ?",
            [q_bytes, k],
        ).fetchall()

    return [
        (r[0], round(1 - r[1], 6))
        for r in rows
        if r[0] not in deleted_ids
    ]
