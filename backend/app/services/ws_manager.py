"""WebSocket 连接管理与事件广播。"""
from __future__ import annotations

import json

from fastapi import WebSocket

from ..logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """管理所有活跃 WebSocket 连接，支持多客户端并发广播。"""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.debug("WS 客户端已连接，当前连接数: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.debug("WS 客户端已断开，当前连接数: %d", len(self._connections))

    async def broadcast(self, event_type: str, data: dict) -> None:
        """向所有在线客户端广播 JSON 事件，单个断开不影响其他客户端。"""
        if not self._connections:
            logger.debug("WS 广播跳过：无在线客户端 event=%s", event_type)
            return
        payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        dead: list[WebSocket] = []
        logger.debug("WS 广播开始 event=%s connections=%d", event_type, len(self._connections))
        for ws in list(self._connections):
            try:
                await ws.send_text(payload)
            except Exception:
                logger.exception("WS 广播失败 event=%s", event_type)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        logger.debug("WS 广播完成 event=%s dead=%d active=%d", event_type, len(dead), len(self._connections))


# 模块级单例，所有 router 和 worker 共用同一个 manager 实例
manager = ConnectionManager()
