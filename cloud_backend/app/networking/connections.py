"""Live agent connection registry (process-local).

Maps device_id -> active WebSocket so the orchestration layer can push
command.dispatch messages in Phase 3+. Durable state (sessions, status)
always goes to the store; this is only the live socket index.
"""

from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: dict[str, WebSocket] = {}

    def register(self, device_id: str, ws: WebSocket) -> None:
        self._sockets[device_id] = ws

    def unregister(self, device_id: str) -> None:
        self._sockets.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._sockets

    async def send(self, device_id: str, text: str) -> bool:
        ws = self._sockets.get(device_id)
        if ws is None:
            return False
        await ws.send_text(text)
        return True

    async def disconnect(self, device_id: str, code: int = 4403) -> None:
        """Force-close a device's socket (e.g. after revocation). The agent's
        reconnect is then rejected and it asks its user to pair again."""
        ws = self._sockets.pop(device_id, None)
        if ws is not None:
            try:
                await ws.close(code=code)
            except Exception:
                pass

    @property
    def connected_devices(self) -> list[str]:
        return list(self._sockets)


manager = ConnectionManager()
