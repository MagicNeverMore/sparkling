"""后台清理任务。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ...logger import get_logger
from ...models import ThoughtAtom
from ...vector_store import delete_vectors, vec_table_exists

logger = get_logger(__name__)

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
    """清理 vec_atoms 中的向量记录（vec_atoms 不受外键级联约束）。"""
    if not vec_table_exists():
        return
    delete_vectors(atom_ids)
