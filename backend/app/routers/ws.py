"""WebSocket 路由：维持长连接，通过 ConnectionManager 接收广播事件。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..logger import get_logger
from ..services.ws_manager import manager
from ..services import auth as auth_service

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    token = websocket.cookies.get(auth_service.SESSION_COOKIE_NAME)
    if auth_service.get_user_by_session(token) is None:
        logger.warning("WS 连接被拒绝：未认证 client=%s", websocket.client)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    logger.info("WS 连接通过认证 client=%s", websocket.client)
    await manager.connect(websocket)
    try:
        while True:
            # 保持连接存活；客户端发来的消息目前忽略（仅服务端推送模式）
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WS 连接已断开 client=%s", websocket.client)
