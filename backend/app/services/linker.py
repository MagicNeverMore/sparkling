"""关联发现服务：基于 KNN 相似度发现并持久化 thought_link。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TypedDict

from ..db import SessionLocal
from ..logger import get_logger
from ..models import Settings, ThoughtAtom, ThoughtLink
from .embedding import knn_by_existing_embedding
from .settings_snapshot import LinkSettingsSnapshot, snapshot_link_settings
from .ws_manager import ConnectionManager

logger = get_logger(__name__)
LinkSettings = Settings | LinkSettingsSnapshot


class LinkEvent(TypedDict):
    event_type: str
    data: dict


async def discover_links(
    atom_id: str,
    settings: LinkSettings,
    manager: ConnectionManager,
    top_k: int = 10,
    expected_version: int | None = None,
) -> list[LinkEvent]:
    """发现与 atom_id 相关的语义关联并持久化。

    流程：
    1. 从 vec_atoms 取已存向量做 KNN（不重新 embed）
    2. 按阈值分流：>= auto → 自动确认；[suggest, auto) → 建议；低于 suggest → 丢弃
    3. 规范化 from/to 顺序，避免重复 link
    4. 已存在且用户手动操作（source=user 或 ignored）的不覆盖
    5. 广播 link.created 或 link.suggested 事件
    """
    link_settings = (
        snapshot_link_settings(settings)
        if isinstance(settings, Settings)
        else settings
    )
    events: list[LinkEvent] = []

    with SessionLocal() as session:
        atom = session.get(ThoughtAtom, atom_id)
        if atom is None or atom.status == "deleted":
            logger.debug("atom %s 不存在或已删除，跳过 link_discover", atom_id)
            return []
        if expected_version is not None and expected_version != atom.version:
            logger.info(
                "atom %s link_discover 任务版本过期，payload=%s current=%s",
                atom_id,
                expected_version,
                atom.version,
            )
            return []

        candidates = knn_by_existing_embedding(atom_id, top_k)
        if not candidates:
            return []

        auto_threshold = link_settings.link_threshold_auto
        suggest_threshold = link_settings.link_threshold_suggest

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
                # 用户已手动操作过，不覆盖；AI 自动确认的 link 可以随阈值升/降级
                if existing.user_ignored or existing.source == "user":
                    continue
                source = "ai_auto" if is_auto else "ai_suggested"
                existing.confidence = similarity
                existing.source = source
                existing.user_confirmed = is_auto
                event_type = "link.created" if is_auto else "link.suggested"
                data = {
                    "id": existing.id,
                    "from_atom_id": from_id,
                    "to_atom_id": to_id,
                    "link_type": "semantic",
                    "confidence": similarity,
                    "source": source,
                    "user_confirmed": is_auto,
                }
                session.commit()
                events.append({"event_type": event_type, "data": data})
                continue

            link_id = str(uuid.uuid4())
            source = "ai_auto" if is_auto else "ai_suggested"
            link = ThoughtLink(
                id=link_id,
                from_atom_id=from_id,
                to_atom_id=to_id,
                link_type="semantic",
                confidence=similarity,
                source=source,
                user_confirmed=is_auto,
                user_ignored=False,
                created_at=datetime.utcnow(),
            )
            session.add(link)
            event_type = "link.created" if is_auto else "link.suggested"
            data = {
                "id": link_id,
                "from_atom_id": from_id,
                "to_atom_id": to_id,
                "link_type": "semantic",
                "confidence": similarity,
                "source": source,
                "user_confirmed": is_auto,
            }
            session.commit()
            events.append({"event_type": event_type, "data": data})
            logger.debug(
                "关联已创建 %s → %s，similarity=%.4f，event=%s",
                from_id, to_id, similarity, event_type,
            )

    for event in events:
        await manager.broadcast(event["event_type"], event["data"])

    return events
