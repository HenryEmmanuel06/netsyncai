"""PostgREST-backed device store for production.

Uses the Supabase REST API with the service-role key so the coordinator can
operate on devices regardless of RLS (the coordinator still scopes every
query by owner_id; agents never see this key).

Pairing codes and device credentials are stored only as SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.schemas.devices import DeviceRegisterRequest, DeviceResponse
from app.services.device_registry import DeviceNotFound, PairingError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _new_code() -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


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

    # ── registry ──

    async def list_devices(self, owner_id: str) -> list[DeviceResponse]:
        r = await self._client.get("/devices", params={"owner_id": f"eq.{owner_id}"})
        r.raise_for_status()
        return [DeviceResponse(**row) for row in r.json()]

    async def get_device(self, owner_id: str, device_id: str) -> DeviceResponse:
        return await self._fetch_device(device_id, owner_id)

    async def get_device_by_id(self, device_id: str) -> DeviceResponse:
        return await self._fetch_device(device_id)

    async def _fetch_device(self, device_id: str, owner_id: str | None = None) -> DeviceResponse:
        params = {"id": f"eq.{device_id}"}
        if owner_id:
            params["owner_id"] = f"eq.{owner_id}"
        r = await self._client.get("/devices", params=params)
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
        body: dict = {"status": status}
        if status != "offline":
            body["last_seen_at"] = _now().isoformat()
        r = await self._client.patch(
            "/devices", params={"id": f"eq.{device_id}"}, json=body,
        )
        r.raise_for_status()
        return DeviceResponse(**r.json()[0])

    async def revoke(self, owner_id: str, device_id: str) -> DeviceResponse:
        await self.get_device(owner_id, device_id)
        r = await self._client.patch(
            "/devices",
            params={"id": f"eq.{device_id}"},
            json={"revoked_at": _now().isoformat(), "status": "offline"},
        )
        r.raise_for_status()
        return DeviceResponse(**r.json()[0])

    # ── pairing ──

    async def create_pairing(
        self, owner_id: str, device_name: str, ttl_seconds: int
    ) -> tuple[str, datetime]:
        code = _new_code()
        expires = _now() + timedelta(seconds=ttl_seconds)
        r = await self._client.post(
            "/device_pairing_requests",
            json={
                "owner_id": owner_id,
                "device_name": device_name,
                "code_hash": _hash(code),
                "expires_at": expires.isoformat(),
            },
        )
        r.raise_for_status()
        return code, expires

    async def redeem_pairing(
        self, code: str, agent_version: str | None
    ) -> tuple[DeviceResponse, str]:
        r = await self._client.get(
            "/device_pairing_requests",
            params={"code_hash": f"eq.{_hash(code.strip().upper())}"},
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise PairingError("invalid pairing code")
        rec = rows[0]
        if rec["used_at"]:
            raise PairingError("pairing code already used")
        if datetime.fromisoformat(rec["expires_at"]) <= _now():
            raise PairingError("pairing code expired")

        # claim it first so a concurrent redeem loses the race
        r = await self._client.patch(
            "/device_pairing_requests",
            params={"id": f"eq.{rec['id']}", "used_at": "is.null"},
            json={"used_at": _now().isoformat()},
        )
        r.raise_for_status()
        if not r.json():
            raise PairingError("pairing code already used")

        credential = secrets.token_urlsafe(32)
        r = await self._client.post(
            "/devices",
            json={
                "owner_id": rec["owner_id"],
                "name": rec["device_name"],
                "platform": "windows",
                "agent_version": agent_version,
                "credential_hash": _hash(credential),
            },
        )
        r.raise_for_status()
        return DeviceResponse(**r.json()[0]), credential

    async def verify_device_credential(self, device_id: str, credential: str) -> bool:
        r = await self._client.get(
            "/devices",
            params={
                "id": f"eq.{device_id}",
                "credential_hash": f"eq.{_hash(credential)}",
                "select": "id",
            },
        )
        r.raise_for_status()
        return len(r.json()) == 1

    # ── agent sessions ──

    async def agent_connected(
        self, device_id: str, status: str, agent_version: str | None,
        lan_address: str | None, lan_port: int | None,
    ) -> None:
        r = await self._client.post(
            "/device_sessions",
            json={
                "device_id": device_id,
                "agent_version": agent_version,
                "lan_address": lan_address,
                "lan_port": lan_port,
                "last_heartbeat_at": _now().isoformat(),
            },
        )
        r.raise_for_status()
        body: dict = {"status": status, "last_seen_at": _now().isoformat()}
        if agent_version:
            body["agent_version"] = agent_version
        r = await self._client.patch(
            "/devices", params={"id": f"eq.{device_id}"}, json=body,
        )
        r.raise_for_status()

    async def agent_disconnected(self, device_id: str) -> None:
        # close the most recent open session
        r = await self._client.get(
            "/device_sessions",
            params={
                "device_id": f"eq.{device_id}",
                "disconnected_at": "is.null",
                "order": "connected_at.desc",
                "limit": 1,
            },
        )
        r.raise_for_status()
        for row in r.json():
            await self._client.patch(
                "/device_sessions",
                params={"id": f"eq.{row['id']}"},
                json={"disconnected_at": _now().isoformat()},
            )
        r = await self._client.patch(
            "/devices", params={"id": f"eq.{device_id}"}, json={"status": "offline"},
        )
        r.raise_for_status()
