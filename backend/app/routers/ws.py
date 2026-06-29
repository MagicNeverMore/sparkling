"""WebSocket 路由：维持长连接，通过 ConnectionManager 接收广播事件。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.ws_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            # 保持连接存活；客户端发来的消息目前忽略（仅服务端推送模式）
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
