"""WebSocket 路由 —— 占位，Task #6 实现真实事件广播。"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            # 占位：保持连接，后续广播会从 services 推送
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
