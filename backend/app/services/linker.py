"""关联发现服务：基于 KNN 相似度发现并持久化 thought_link。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..logger import get_logger
from ..models import Settings, ThoughtLink
from .embedding import knn_by_existing_embedding
from .ws_manager import ConnectionManager

logger = get_logger(__name__)


async def discover_links(
    session: Session,
    atom_id: str,
    settings: Settings,
    manager: ConnectionManager,
    top_k: int = 10,
) -> list[ThoughtLink]:
    """发现与 atom_id 相关的语义关联并持久化。

    流程：
    1. 从 vec_atoms 取已存向量做 KNN（不重新 embed）
    2. 按阈值分流：>= auto → 自动确认；[suggest, auto) → 建议；低于 suggest → 丢弃
    3. 规范化 from/to 顺序，避免重复 link
    4. 已存在且用户已操作（confirmed/ignored）的不覆盖
    5. 广播 link.created 或 link.suggested 事件
    """
    candidates = knn_by_existing_embedding(atom_id, top_k)
    if not candidates:
        return []

    auto_threshold = settings.link_threshold_auto
    suggest_threshold = settings.link_threshold_suggest
    created: list[ThoughtLink] = []

    for neighbor_id, similarity in candidates:
        if similarity < suggest_threshold:
            continue

        is_auto = similarity >= auto_threshold
        # 规范化顺序，避免 (A→B) 和 (B→A) 生成重复 link
        from_id, to_id = sorted([atom_id, neighbor_id])

        existing = (
            session.query(ThoughtLink)
            .filter_by(from_atom_id=from_id, to_atom_id=to_id, link_type="semantic")
            .first()
        )
        if existing:
            # 用户已手动操作过，不覆盖
            if existing.user_confirmed or existing.user_ignored:
                continue
            # 只更新置信度
            existing.confidence = similarity
            session.commit()
            continue

        link = ThoughtLink(
            id=str(uuid.uuid4()),
            from_atom_id=from_id,
            to_atom_id=to_id,
            link_type="semantic",
            confidence=similarity,
            source="ai_auto" if is_auto else "ai_suggested",
            user_confirmed=is_auto,
            user_ignored=False,
            created_at=datetime.utcnow(),
        )
        session.add(link)
        session.commit()

        event_type = "link.created" if is_auto else "link.suggested"
        await manager.broadcast(event_type, {
            "id": link.id,
            "from_atom_id": link.from_atom_id,
            "to_atom_id": link.to_atom_id,
            "link_type": link.link_type,
            "confidence": link.confidence,
            "source": link.source,
            "user_confirmed": link.user_confirmed,
        })
        created.append(link)
        logger.debug(
            "关联已创建 %s → %s，similarity=%.4f，event=%s",
            from_id, to_id, similarity, event_type,
        )

    return created
