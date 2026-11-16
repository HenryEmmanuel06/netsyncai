"""Device registry — storage-agnostic service layer.

Two backends:
- InMemoryDeviceStore: dev/tests, no external services.
- SupabaseDeviceStore (services/supabase_store.py): PostgREST, production.

Swap via the `device_store` setting.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.schemas.devices import DeviceRegisterRequest, DeviceResponse


class DeviceNotFound(Exception):
    pass


class PairingError(Exception):
    """Invalid, expired, or already-consumed pairing code."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_pairing_code() -> str:
    """8 chars from an unambiguous alphabet (no 0/O, 1/I/L)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def new_device_credential() -> str:
    return secrets.token_urlsafe(32)


class DeviceStore(Protocol):
    # ── registry (owner-scoped) ──
    async def list_devices(self, owner_id: str) -> list[DeviceResponse]: ...
    async def get_device(self, owner_id: str, device_id: str) -> DeviceResponse: ...
    async def register(self, owner_id: str, req: DeviceRegisterRequest) -> DeviceResponse: ...
    async def set_status(self, owner_id: str, device_id: str, status: str) -> DeviceResponse: ...
    async def revoke(self, owner_id: str, device_id: str) -> DeviceResponse: ...

    # ── internal (not owner-scoped; used by pairing + agent WS) ──
    async def get_device_by_id(self, device_id: str) -> DeviceResponse: ...
    async def create_pairing(
        self, owner_id: str, device_name: str, ttl_seconds: int
    ) -> tuple[str, datetime]: ...
    async def redeem_pairing(
        self, code: str, agent_version: str | None
    ) -> tuple[DeviceResponse, str]: ...
    async def verify_device_credential(self, device_id: str, credential: str) -> bool: ...
    async def agent_connected(
        self, device_id: str, status: str, agent_version: str | None,
        lan_address: str | None, lan_port: int | None,
    ) -> None: ...
    async def agent_disconnected(self, device_id: str) -> None: ...


class InMemoryDeviceStore:
    """Deterministic store for unit tests and local dev."""

    def __init__(self) -> None:
        self._devices: dict[str, dict] = {}
        self._pairing: dict[str, dict] = {}   # code_hash -> record
        self._sessions: dict[str, dict] = {}  # device_id -> session

    # ── registry ──

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

    async def get_device_by_id(self, device_id: str) -> DeviceResponse:
        d = self._devices.get(device_id)
        if not d:
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
            "credential_hash": None,
        }
        return DeviceResponse(**self._devices[device_id])

    async def set_status(self, owner_id: str, device_id: str, status: str) -> DeviceResponse:
        await self.get_device(owner_id, device_id)
        d = self._devices[device_id]
        d["status"] = status
        if status != "offline":
            d["last_seen_at"] = _now()
        return DeviceResponse(**d)

    async def revoke(self, owner_id: str, device_id: str) -> DeviceResponse:
        await self.get_device(owner_id, device_id)
        d = self._devices[device_id]
        d["revoked_at"] = _now()
        d["status"] = "offline"
        return DeviceResponse(**d)

    # ── pairing ──

    async def create_pairing(
        self, owner_id: str, device_name: str, ttl_seconds: int
    ) -> tuple[str, datetime]:
        code = new_pairing_code()
        expires = _now() + timedelta(seconds=ttl_seconds)
        self._pairing[_hash_secret(code)] = {
            "owner_id": owner_id,
            "device_name": device_name,
            "expires_at": expires,
            "used": False,
        }
        return code, expires

    async def redeem_pairing(
        self, code: str, agent_version: str | None
    ) -> tuple[DeviceResponse, str]:
        record = self._pairing.get(_hash_secret(code.strip().upper()))
        if not record:
            raise PairingError("invalid pairing code")
        if record["used"]:
            raise PairingError("pairing code already used")
        if record["expires_at"] <= _now():
            raise PairingError("pairing code expired")
        record["used"] = True

        credential = new_device_credential()
        device_id = str(uuid.uuid4())
        self._devices[device_id] = {
            "id": device_id,
            "owner_id": record["owner_id"],
            "name": record["device_name"],
            "platform": "windows",
            "agent_version": agent_version,
            "status": "offline",
            "last_seen_at": None,
            "revoked_at": None,
            "created_at": _now(),
            "credential_hash": _hash_secret(credential),
        }
        return DeviceResponse(**self._devices[device_id]), credential

    async def verify_device_credential(self, device_id: str, credential: str) -> bool:
        d = self._devices.get(device_id)
        if not d or not d.get("credential_hash"):
            return False
        return secrets.compare_digest(d["credential_hash"], _hash_secret(credential))

    # ── agent sessions ──

    async def agent_connected(
        self, device_id: str, status: str, agent_version: str | None,
        lan_address: str | None, lan_port: int | None,
    ) -> None:
        d = self._devices[device_id]
        d["status"] = status
        d["last_seen_at"] = _now()
        if agent_version:
            d["agent_version"] = agent_version
        self._sessions[device_id] = {
            "connected_at": _now(),
            "last_heartbeat_at": _now(),
            "agent_version": agent_version,
            "lan_address": lan_address,
            "lan_port": lan_port,
        }

    async def agent_disconnected(self, device_id: str) -> None:
        self._sessions.pop(device_id, None)
        if device_id in self._devices:
            self._devices[device_id]["status"] = "offline"
