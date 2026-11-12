import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, org_id: str, websocket: WebSocket):
        await websocket.accept()
        if org_id not in self.active_connections:
            self.active_connections[org_id] = []
        self.active_connections[org_id].append(websocket)

    def disconnect(self, org_id: str, websocket: WebSocket):
        if org_id in self.active_connections:
            if websocket in self.active_connections[org_id]:
                self.active_connections[org_id].remove(websocket)

    async def broadcast_to_org(self, org_id: str, message: dict[str, Any]):
        if org_id in self.active_connections:
            for connection in list(self.active_connections[org_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(org_id, connection)


manager = ConnectionManager()


@router.websocket("/ws/{org_id}")
async def websocket_endpoint(websocket: WebSocket, org_id: str):
    await manager.connect(org_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo ping-pong or broadcast
            await websocket.send_json({"type": "ack", "payload": data})
    except WebSocketDisconnect:
        manager.disconnect(org_id, websocket)
