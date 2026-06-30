from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.events import event_bus
from shared.constants import EventType

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def _forward_to_websockets(event_type: EventType, payload: dict) -> None:
    await manager.broadcast(
        {
            "type": event_type.value,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )


event_bus.subscribe(_forward_to_websockets)


@router.websocket("/ws/bin-status")
async def bin_status_ws(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json(
            {"type": "connected", "message": "Subscribed to bin status updates"}
        )
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
