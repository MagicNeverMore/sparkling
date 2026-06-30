"""向量存储抽象层：统一 sqlite-vec 和 pgvector 两种后端。"""
from __future__ import annotations

import struct

import sqlite_vec

from .db import get_database_backend, get_raw_conn
from .logger import get_logger

logger = get_logger(__name__)


def vec_table_exists() -> bool:
    if _is_postgresql():
        return _pg_vec_table_exists()
    return _sqlite_vec_table_exists()


def ensure_vec_table(dim: int) -> None:
    if vec_table_exists():
        return
    _do_create_vec_table(dim)
    logger.info("vec_atoms 表已创建（%s），维度=%d", get_database_backend(), dim)


def create_vec_table(dim: int) -> None:
    if _is_postgresql():
        with get_raw_conn() as conn:
            _pg_execute(conn, "DROP TABLE IF EXISTS vec_atoms")
            conn.commit()
    else:
        with get_raw_conn() as conn:
            conn.execute("DROP TABLE IF EXISTS vec_atoms")
            conn.commit()
    _do_create_vec_table(dim)
    logger.info("vec_atoms 表已重建（%s），维度=%d", get_database_backend(), dim)


def upsert_vector(atom_id: str, embedding: list[float]) -> None:
    if _is_postgresql():
        with get_raw_conn() as conn:
            _pg_execute(
                conn,
                "INSERT INTO vec_atoms (atom_id, embedding) VALUES (%s, %s)"
                " ON CONFLICT (atom_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (atom_id, embedding),
            )
            conn.commit()
        return

    vec_bytes = sqlite_vec.serialize_float32(embedding)
    with get_raw_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO vec_atoms(atom_id, embedding) VALUES (?, ?)",
            [atom_id, vec_bytes],
        )
        conn.commit()


def get_vector(atom_id: str) -> bytes | None:
    if _is_postgresql():
        with get_raw_conn() as conn:
            rows = _pg_execute(
                conn,
                "SELECT embedding FROM vec_atoms WHERE atom_id = %s",
                (atom_id,),
            )
            if not rows:
                return None
            return _pg_vector_to_bytes(rows[0][0])

    with get_raw_conn() as conn:
        row = conn.execute(
            "SELECT embedding FROM vec_atoms WHERE atom_id = ?", [atom_id]
        ).fetchone()
        return row[0] if row else None


def knn_search(query_bytes: bytes, k: int, exclude_id: str | None = None) -> list[tuple[str, float]]:
    if _is_postgresql():
        return _pg_knn_search(query_bytes, k, exclude_id)
    return _sqlite_knn_search(query_bytes, k, exclude_id)


def delete_vectors(atom_ids: list[str]) -> None:
    if not atom_ids:
        return
    if _is_postgresql():
        with get_raw_conn() as conn:
            _pg_execute(
                conn,
                "DELETE FROM vec_atoms WHERE atom_id = ANY(%s)",
                (atom_ids,),
            )
            conn.commit()
        return

    placeholders = ",".join("?" for _ in atom_ids)
    with get_raw_conn() as conn:
        conn.execute(
            f"DELETE FROM vec_atoms WHERE atom_id IN ({placeholders})", atom_ids
        )
        conn.commit()


def serialize_vector(vec: list[float]) -> bytes:
    if _is_postgresql():
        return _serialize_float32(vec)
    return sqlite_vec.serialize_float32(vec)


def _is_postgresql() -> bool:
    return get_database_backend() == "postgresql"


def _do_create_vec_table(dim: int) -> None:
    dim = int(dim)
    if _is_postgresql():
        with get_raw_conn() as conn:
            _pg_execute(
                conn,
                "CREATE TABLE vec_atoms ("
                "  atom_id TEXT PRIMARY KEY,"
                f"  embedding vector({dim})"
                ")",
            )
            conn.commit()
        return

    with get_raw_conn() as conn:
        conn.execute(
            f"CREATE VIRTUAL TABLE vec_atoms "
            f"USING vec0(atom_id TEXT PRIMARY KEY, embedding float[{dim}] distance_metric=cosine)"
        )
        conn.commit()


def _sqlite_vec_table_exists() -> bool:
    with get_raw_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_atoms'"
        ).fetchone()
        return row is not None


def _sqlite_knn_search(query_bytes: bytes, k: int, exclude_id: str | None) -> list[tuple[str, float]]:
    with get_raw_conn() as conn:
        if exclude_id:
            rows = conn.execute(
                "SELECT atom_id, distance FROM vec_atoms "
                "WHERE embedding MATCH ? AND k = ? AND atom_id != ?",
                [query_bytes, k, exclude_id],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT atom_id, distance FROM vec_atoms "
                "WHERE embedding MATCH ? AND k = ?",
                [query_bytes, k],
            ).fetchall()
        return [(r[0], float(r[1])) for r in rows]


def _pg_vec_table_exists() -> bool:
    with get_raw_conn() as conn:
        rows = _pg_execute(
            conn,
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
            ("vec_atoms",),
        )
        return bool(rows[0][0])


def _pg_knn_search(query_bytes: bytes, k: int, exclude_id: str | None) -> list[tuple[str, float]]:
    q_vec = _deserialize_float32(query_bytes)
    with get_raw_conn() as conn:
        if exclude_id:
            rows = _pg_execute(
                conn,
                "SELECT atom_id, embedding <=> %s AS distance"
                " FROM vec_atoms"
                " WHERE atom_id != %s"
                " ORDER BY distance"
                " LIMIT %s",
                (q_vec, exclude_id, k),
            )
        else:
            rows = _pg_execute(
                conn,
                "SELECT atom_id, embedding <=> %s AS distance"
                " FROM vec_atoms"
                " ORDER BY distance"
                " LIMIT %s",
                (q_vec, k),
            )
        return [(r[0], float(r[1])) for r in rows]


def _pg_execute(conn, sql: str, params=None):  # noqa: ANN001
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        return cur.fetchall()
    finally:
        cur.close()


def _pg_vector_to_bytes(vec) -> bytes:  # noqa: ANN001
    if isinstance(vec, memoryview):
        return bytes(vec)
    if isinstance(vec, bytes):
        return vec
    return _serialize_float32(list(vec))


def _serialize_float32(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _deserialize_float32(data: bytes) -> list[float]:
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))
