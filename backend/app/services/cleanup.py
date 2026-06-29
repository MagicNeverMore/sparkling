"""后台清理任务。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db import get_raw_conn
from ..models import ThoughtAtom

logger = logging.getLogger(__name__)

SOFT_DELETE_RETENTION_DAYS = 30


def purge_expired_deleted_atoms(session: Session) -> int:
    """硬删除软删除超过保留期的 atom，并清理对应 vec_atoms 记录。"""
    cutoff = datetime.utcnow() - timedelta(days=SOFT_DELETE_RETENTION_DAYS)
    expired_ids = [
        atom_id
        for (atom_id,) in (
            session.query(ThoughtAtom.id)
            .filter(ThoughtAtom.status == "deleted")
            .filter(ThoughtAtom.deleted_at.is_not(None))
            .filter(ThoughtAtom.deleted_at < cutoff)
            .all()
        )
    ]
    if not expired_ids:
        return 0

    _delete_vec_rows(expired_ids)
    deleted_count = (
        session.query(ThoughtAtom)
        .filter(ThoughtAtom.id.in_(expired_ids))
        .delete(synchronize_session=False)
    )
    session.commit()
    logger.info("已硬删除 %d 条超过 %d 天的软删除 atom", deleted_count, SOFT_DELETE_RETENTION_DAYS)
    return deleted_count


def _delete_vec_rows(atom_ids: list[str]) -> None:
    """vec_atoms 是虚表，不受外键级联约束，需要单独清理。"""
    placeholders = ",".join("?" for _ in atom_ids)
    with get_raw_conn() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_atoms'",
        ).fetchone()
        if not exists:
            return
        conn.execute(f"DELETE FROM vec_atoms WHERE atom_id IN ({placeholders})", atom_ids)
        conn.commit()
