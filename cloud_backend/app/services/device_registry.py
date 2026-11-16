"""Device registry — storage-agnostic service layer.

Two backends:
- InMemoryDeviceStore: dev/tests, no external services.
- SupabaseDeviceStore (services/supabase_store.py): PostgREST, production.

Swap via the `device_store` setting. Phase 2 will add session tracking;
the interface already anticipates it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from app.schemas.devices import DeviceRegisterRequest, DeviceResponse


class DeviceNotFound(Exception):
    pass


class DeviceStore(Protocol):
    async def list_devices(self, owner_id: str) -> list[DeviceResponse]: ...
    async def get_device(self, owner_id: str, device_id: str) -> DeviceResponse: ...
    async def register(self, owner_id: str, req: DeviceRegisterRequest) -> DeviceResponse: ...
    async def set_status(self, owner_id: str, device_id: str, status: str) -> DeviceResponse: ...
    async def revoke(self, owner_id: str, device_id: str) -> DeviceResponse: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryDeviceStore:
    """Deterministic store for unit tests and local dev."""

    def __init__(self) -> None:
        self._devices: dict[str, dict] = {}

    async def list_devices(self, owner_id: str) -> list[DeviceResponse]:
        return [
            DeviceResponse(**d)
            for d in self._devices.values()
            if d["owner_id"] == owner_id
        ]

    async def get_device(self, owner_id: str, device_id: str) -> DeviceResponse:
        d = self._devices.get(device_id)
        if not d or d["owner_id"] != owner_id:
            raise DeviceNotFound(device_id)
        return DeviceResponse(**d)

    async def register(self, owner_id: str, req: DeviceRegisterRequest) -> DeviceResponse:
        device_id = str(uuid.uuid4())
        self._devices[device_id] = {
            "id": device_id,
            "owner_id": owner_id,
            "name": req.name,
            "platform": req.platform,
            "agent_version": req.agent_version,
            "status": "offline",
            "last_seen_at": None,
            "revoked_at": None,
            "created_at": _now(),
        }
        return DeviceResponse(**self._devices[device_id])

    async def set_status(self, owner_id: str, device_id: str, status: str) -> DeviceResponse:
        device = await self.get_device(owner_id, device_id)
        d = self._devices[device_id]
        d["status"] = status
        d["last_seen_at"] = _now() if status != "offline" else d["last_seen_at"]
        return DeviceResponse(**d)

    async def revoke(self, owner_id: str, device_id: str) -> DeviceResponse:
        await self.get_device(owner_id, device_id)
        d = self._devices[device_id]
        d["revoked_at"] = _now()
        d["status"] = "offline"
        return DeviceResponse(**d)
