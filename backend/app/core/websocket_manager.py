"""WebSocket connection manager with per-user rooms."""
import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks active websocket connections per user_id and fans out events."""

    def __init__(self) -> None:
        # user_id -> set[WebSocket]
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)
        logger.info("WS connected for user=%s (total=%s)", user_id, self.total_connections)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._connections.pop(user_id, None)
        logger.info("WS disconnected for user=%s", user_id)

    @property
    def total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())

    async def send_to_user(self, user_id: str, event_type: str, data: Any) -> None:
        """Push an event to every socket belonging to a user."""
        payload = json.dumps({"type": event_type, "data": data}, default=str, ensure_ascii=False)
        conns = list(self._connections.get(user_id, set()))
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001 - best effort broadcast
                logger.exception("Failed to push WS event to user=%s", user_id)
                await self.disconnect(user_id, ws)

    async def broadcast(self, event_type: str, data: Any) -> None:
        payload = json.dumps({"type": event_type, "data": data}, default=str, ensure_ascii=False)
        for user_id, conns in list(self._connections.items()):
            for ws in list(conns):
                try:
                    await ws.send_text(payload)
                except Exception:  # noqa: BLE001
                    await self.disconnect(user_id, ws)


manager = ConnectionManager()
