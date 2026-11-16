"""PostgREST-backed device store for production.

Uses the Supabase REST API with the service-role key so the coordinator can
operate on devices regardless of RLS (the coordinator still scopes every
query by owner_id; agents never see this key).

Phase 1 implements the device table only. Later phases add pairing,
permissions, tasks, transfers against the same client.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.schemas.devices import DeviceRegisterRequest, DeviceResponse
from app.services.device_registry import DeviceNotFound


class SupabaseDeviceStore:
    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError(
                "SupabaseDeviceStore requires SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY"
            )
        self._client = httpx.AsyncClient(
            base_url=f"{settings.supabase_url.rstrip('/')}/rest/v1",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=10.0,
        )

    async def list_devices(self, owner_id: str) -> list[DeviceResponse]:
        r = await self._client.get("/devices", params={"owner_id": f"eq.{owner_id}"})
        r.raise_for_status()
        return [DeviceResponse(**row) for row in r.json()]

    async def get_device(self, owner_id: str, device_id: str) -> DeviceResponse:
        r = await self._client.get(
            "/devices",
            params={"id": f"eq.{device_id}", "owner_id": f"eq.{owner_id}"},
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise DeviceNotFound(device_id)
        return DeviceResponse(**rows[0])

    async def register(self, owner_id: str, req: DeviceRegisterRequest) -> DeviceResponse:
        r = await self._client.post(
            "/devices",
            json={
                "owner_id": owner_id,
                "name": req.name,
                "platform": req.platform,
                "agent_version": req.agent_version,
            },
        )
        r.raise_for_status()
        return DeviceResponse(**r.json()[0])

    async def set_status(self, owner_id: str, device_id: str, status: str) -> DeviceResponse:
        await self.get_device(owner_id, device_id)
        r = await self._client.patch(
            "/devices",
            params={"id": f"eq.{device_id}"},
            json={"status": status},
        )
        r.raise_for_status()
        return DeviceResponse(**r.json()[0])

    async def revoke(self, owner_id: str, device_id: str) -> DeviceResponse:
        from datetime import datetime, timezone

        await self.get_device(owner_id, device_id)
        r = await self._client.patch(
            "/devices",
            params={"id": f"eq.{device_id}"},
            json={
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "status": "offline",
            },
        )
        r.raise_for_status()
        return DeviceResponse(**r.json()[0])
