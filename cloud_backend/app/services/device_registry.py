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


class GrantError(Exception):
    """Sharing/access-request violation — maps to 409/403 at the API layer."""


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

    # ── sync sessions ──
    async def create_sync(
        self, owner_id: str, a_device_id: str, a_path: str,
        b_device_id: str | None, b_path: str | None, mode: str,
        state: str = "active", pending_user_id: str | None = None,
    ) -> dict: ...
    async def list_sync(self, owner_id: str) -> list[dict]: ...
    async def set_sync_state(self, owner_id: str, session_id: str, state: str) -> dict: ...
    async def add_sync_participant(
        self, session_id: str, device_id: str, root_path: str
    ) -> dict:
        """Join the accepting user's side to a pending request session."""
        ...
    async def get_sync_participants(self, session_id: str) -> list[dict]: ...
    async def get_active_syncs_for_device(self, device_id: str) -> list[dict]: ...

    # ── sharing & permissions ──
    async def create_shared_folder(
        self, owner_id: str, device_id: str, label: str, root_path: str
    ) -> dict: ...
    async def list_shares_owned(self, owner_id: str) -> list[dict]: ...
    async def list_shares_granted(self, user_id: str) -> list[dict]: ...
    async def add_grant(
        self, folder_id: str, subject_user_id: str, permissions: int, granted_by: str
    ) -> dict: ...
    async def revoke_grant(self, folder_id: str, grant_id: str, owner_id: str) -> None: ...
    async def list_grants(self, folder_id: str) -> list[dict]: ...
    async def delete_share(self, owner_id: str, folder_id: str) -> None: ...
    async def delete_shares_for_root(
        self, owner_id: str, device_id: str, root_path: str
    ) -> int:
        """Delete every share record on device+path (grants go with them) —
        called when the owner removes the folder on the agent. Returns the
        number of shares removed."""
        ...
    async def effective_permissions(
        self, user_id: str, device_id: str, path: str
    ) -> int:
        """Bitmask of all grant permissions for user on shared folders of
        device_id whose root_path prefixes `path`. 0 = no access."""
        ...
    async def granted_roots(self, user_id: str, device_id: str) -> list[dict]:
        """[{root_path, permissions}] a non-owner user holds on this device."""
        ...
    async def get_share(self, folder_id: str) -> dict | None: ...
    async def resolve_user(self, subject: str) -> str | None:
        """email/handle/uuid -> user_id (supabase impl resolves; memory
        impl accepts uuid strings)."""
        ...

    # ── pairing preview + activity ──
    async def preview_pairing(self, code: str) -> dict:
        """{device_name, owner_email, expires_at} without consuming the
        code. Raises PairingError when invalid/used/expired."""
        ...
    async def record_activity(
        self, actor_id: str | None, action: str, *, device_id: str | None = None,
        target: str | None = None, metadata: dict | None = None,
    ) -> None: ...
    async def list_activity(self, actor_id: str, limit: int = 50) -> list[dict]: ...

    # ── file tags + profile preferences ──
    async def add_tag(
        self, user_id: str, device_id: str, path: str, tag: str
    ) -> dict: ...
    async def remove_tag(
        self, user_id: str, device_id: str, path: str, tag: str
    ) -> None: ...
    async def list_tags(self, user_id: str, device_id: str) -> dict[str, list[str]]:
        """{path: [tag, ...]} — the caller maps them onto browsed entries."""
        ...
    async def get_preferences(self, user_id: str) -> dict: ...
    async def set_preferences(self, user_id: str, prefs: dict) -> dict: ...
    async def ensure_profile(self, user_id: str, email: str) -> None: ...

    # ── access requests + user blocking ───────────────────────────────────
    async def request_access(self, requester_id: str, folder_id: str, role: str) -> dict: ...
    async def list_access_requests(self, user_id: str, direction: str) -> list[dict]: ...
    async def resolve_access_request(
        self, owner_id: str, request_id: str, approve: bool, permissions: int
    ) -> dict: ...
    async def block_user(self, blocker_id: str, subject_id: str) -> None: ...
    async def unblock_user(self, blocker_id: str, subject_id: str) -> None: ...
    async def list_blocked(self, blocker_id: str) -> list[dict]: ...


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
        self, owner_id: str, device_name: str, ttl_seconds: int,
        owner_email: str | None = None,
    ) -> tuple[str, datetime]:
        code = new_pairing_code()
        expires = _now() + timedelta(seconds=ttl_seconds)
        self._pairing[_hash_secret(code)] = {
            "owner_id": owner_id,
            "owner_email": owner_email,
            "device_name": device_name,
            "expires_at": expires,
            "used": False,
        }
        return code, expires

    def _valid_pairing(self, code: str) -> dict:
        record = self._pairing.get(_hash_secret(code.strip().upper()))
        if not record:
            raise PairingError("invalid pairing code")
        if record["used"]:
            raise PairingError("pairing code already used")
        if record["expires_at"] <= _now():
            raise PairingError("pairing code expired")
        return record

    async def preview_pairing(self, code: str) -> dict:
        r = self._valid_pairing(code)
        return {"device_name": r["device_name"], "owner_email": r.get("owner_email"),
                "expires_at": r["expires_at"]}

    async def record_activity(
        self, actor_id: str | None, action: str, *, device_id: str | None = None,
        target: str | None = None, metadata: dict | None = None,
    ) -> None:
        if not hasattr(self, "_activity"):
            self._activity = []
        self._activity.append({
            "id": len(self._activity) + 1, "actor_id": actor_id,
            "device_id": device_id, "action": action, "target": target,
            "metadata": metadata or {}, "created_at": _now(),
        })
        del self._activity[:-1000]  # bounded in dev

    async def list_activity(self, actor_id: str, limit: int = 50) -> list[dict]:
        rows = [a for a in getattr(self, "_activity", []) if a["actor_id"] == actor_id]
        return list(reversed(rows))[:limit]

    # ── file tags + preferences ──

    async def add_tag(
        self, user_id: str, device_id: str, path: str, tag: str
    ) -> dict:
        if not hasattr(self, "_tags"):
            self._tags = {}
        self._tags.setdefault((user_id, device_id, path), set()).add(tag)
        return {"path": path, "tag": tag}

    async def remove_tag(
        self, user_id: str, device_id: str, path: str, tag: str
    ) -> None:
        tags = getattr(self, "_tags", {}).get((user_id, device_id, path))
        if tags:
            tags.discard(tag)

    async def list_tags(self, user_id: str, device_id: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for (uid, did, path), tags in getattr(self, "_tags", {}).items():
            if uid == user_id and did == device_id and tags:
                out[path] = sorted(tags)
        return out

    async def get_preferences(self, user_id: str) -> dict:
        if not hasattr(self, "_prefs"):
            self._prefs = {}
        return self._prefs.get(user_id, {"display_name": "", "discoverable": True})

    async def set_preferences(self, user_id: str, prefs: dict) -> dict:
        if not hasattr(self, "_prefs"):
            self._prefs = {}
        cur = self._prefs.get(user_id, {"display_name": "", "discoverable": True})
        cur.update({k: v for k, v in prefs.items() if k in cur})
        self._prefs[user_id] = cur
        return cur

    async def ensure_profile(self, user_id: str, email: str) -> None:
        pass  # in-memory store has no FK constraints

    async def redeem_pairing(
        self, code: str, agent_version: str | None
    ) -> tuple[DeviceResponse, str]:
        record = self._valid_pairing(code)
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

    # ── sync sessions ──

    async def create_sync(
        self, owner_id: str, a_device_id: str, a_path: str,
        b_device_id: str | None, b_path: str | None, mode: str,
        state: str = "active", pending_user_id: str | None = None,
    ) -> dict:
        session_id = str(uuid.uuid4())
        participants = [{"device_id": a_device_id, "root": a_path}]
        if b_device_id is not None:
            participants.append({"device_id": b_device_id, "root": b_path})
        session = {
            "id": session_id,
            "name": " ↔ ".join(p["root"] for p in participants),
            "mode": mode,
            "state": state,
            "created_by": owner_id,
            "created_at": _now(),
            "pending_user_id": pending_user_id,
            "participants": participants,
        }
        if not hasattr(self, "_sync"):
            self._sync = {}
        self._sync[session_id] = session
        return {k: v for k, v in session.items()}

    async def get_sync(self, session_id: str) -> dict:
        s = getattr(self, "_sync", {}).get(session_id)
        if not s:
            raise DeviceNotFound(session_id)
        return s

    async def list_sync(self, owner_id: str) -> list[dict]:
        # sessions I created, that involve one of my devices, or that were
        # addressed to me and are waiting for my acceptance
        mine = {d["id"] for d in self._devices.values() if d["owner_id"] == owner_id}
        return [
            s for s in getattr(self, "_sync", {}).values()
            if s["created_by"] == owner_id
            or s.get("pending_user_id") == owner_id
            or any(p["device_id"] in mine for p in s["participants"])
        ]

    async def set_sync_state(self, actor_id: str, session_id: str, state: str) -> dict:
        s = getattr(self, "_sync", {}).get(session_id)
        if not s:
            raise DeviceNotFound(session_id)
        if s["created_by"] != actor_id and s.get("pending_user_id") != actor_id and not any(
            self._devices.get(p["device_id"], {}).get("owner_id") == actor_id
            for p in s["participants"]
        ):
            raise DeviceNotFound(session_id)  # can't even see the session
        s["state"] = state
        return s

    async def add_sync_participant(
        self, session_id: str, device_id: str, root_path: str
    ) -> dict:
        s = getattr(self, "_sync", {}).get(session_id)
        if not s:
            raise DeviceNotFound(session_id)
        if all(p["device_id"] != device_id for p in s["participants"]):
            s["participants"].append({"device_id": device_id, "root": root_path})
        s["pending_user_id"] = None
        s["name"] = " ↔ ".join(p["root"] for p in s["participants"])
        return s

    async def get_sync_participants(self, session_id: str) -> list[dict]:
        s = getattr(self, "_sync", {}).get(session_id)
        return s["participants"] if s else []

    async def get_active_syncs_for_device(self, device_id: str) -> list[dict]:
        """Active sessions this device participates in — used to re-issue
        start_sync after an agent reconnects."""
        out = []
        for s in getattr(self, "_sync", {}).values():
            if s["state"] != "active":
                continue
            for p in s["participants"]:
                if p["device_id"] == device_id:
                    peer = next(
                        q["device_id"] for q in s["participants"]
                        if q["device_id"] != device_id
                    )
                    out.append({
                        "session_id": s["id"], "root": p["root"],
                        "peer_device_id": peer, "mode": s["mode"],
                    })
        return out

    # ── sharing & permissions ──

    async def create_shared_folder(
        self, owner_id: str, device_id: str, label: str, root_path: str
    ) -> dict:
        if not hasattr(self, "_shares"):
            self._shares = {}
            self._grants = {}
        share = {
            "id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "device_id": device_id,
            "device_name": self._devices.get(device_id, {}).get("name", ""),
            "label": label or root_path,
            "root_path": root_path,
            "created_at": _now(),
        }
        self._shares[share["id"]] = share
        return share

    async def list_shares_owned(self, owner_id: str) -> list[dict]:
        return [
            s for s in getattr(self, "_shares", {}).values()
            if s["owner_id"] == owner_id
        ]

    async def list_shares_granted(self, user_id: str) -> list[dict]:
        out = []
        for g in getattr(self, "_grants", {}).values():
            if g["subject_user_id"] != user_id:
                continue
            share = getattr(self, "_shares", {}).get(g["folder_id"])
            if share and not self._is_blocked(share["owner_id"], user_id):
                out.append({**share, "permissions": g["permissions_granted"],
                            "grant_id": g["id"]})
        return out

    async def add_grant(
        self, folder_id: str, subject_user_id: str, permissions: int, granted_by: str
    ) -> dict:
        share = getattr(self, "_shares", {}).get(folder_id)
        if not share:
            raise DeviceNotFound(folder_id)
        grant = {
            "id": str(uuid.uuid4()),
            "folder_id": folder_id,
            "subject_user_id": subject_user_id,
            "permissions_granted": permissions,
            "granted_by": granted_by,
            "created_at": _now(),
        }
        self._grants[grant["id"]] = grant
        return grant

    async def revoke_grant(self, folder_id: str, grant_id: str, owner_id: str) -> None:
        grant = getattr(self, "_grants", {}).get(grant_id)
        share = getattr(self, "_shares", {}).get(folder_id)
        if not grant or not share or share["owner_id"] != owner_id:
            raise DeviceNotFound(grant_id)
        del self._grants[grant_id]

    async def list_grants(self, folder_id: str) -> list[dict]:
        return [
            g for g in getattr(self, "_grants", {}).values()
            if g["folder_id"] == folder_id
        ]

    async def delete_share(self, owner_id: str, folder_id: str) -> None:
        share = getattr(self, "_shares", {}).get(folder_id)
        if not share or share["owner_id"] != owner_id:
            raise DeviceNotFound(folder_id)
        del self._shares[folder_id]
        for gid in [g["id"] for g in self._grants.values() if g["folder_id"] == folder_id]:
            del self._grants[gid]

    async def delete_shares_for_root(
        self, owner_id: str, device_id: str, root_path: str
    ) -> int:
        norm = root_path.replace("/", "\\").lower().rstrip("\\")
        doomed = [
            s["id"] for s in getattr(self, "_shares", {}).values()
            if s["owner_id"] == owner_id and s["device_id"] == device_id
            and s["root_path"].replace("/", "\\").lower().rstrip("\\") == norm
        ]
        for folder_id in doomed:
            await self.delete_share(owner_id, folder_id)
            for rid in [r["id"] for r in getattr(self, "_access_requests", {}).values()
                        if r["folder_id"] == folder_id]:
                del self._access_requests[rid]
        return len(doomed)

    async def effective_permissions(
        self, user_id: str, device_id: str, path: str
    ) -> int:
        bits = 0
        norm = path.replace("/", "\\").lower().rstrip("\\")
        for g in getattr(self, "_grants", {}).values():
            if g["subject_user_id"] != user_id:
                continue
            share = getattr(self, "_shares", {}).get(g["folder_id"])
            if not share or share["device_id"] != device_id:
                continue
            root = share["root_path"].replace("/", "\\").lower().rstrip("\\")
            if norm == root or norm.startswith(root + "\\"):
                bits |= g["permissions_granted"]
            if self._is_blocked(share["owner_id"], user_id):
                bits = 0
        return bits

    def _is_blocked(self, owner_id: str, user_id: str) -> bool:
        return user_id in getattr(self, "_blocked", {}).get(owner_id, set())

    async def granted_roots(self, user_id: str, device_id: str) -> list[dict]:
        """[{root_path, permissions}] the user has on this device."""
        out = []
        for g in getattr(self, "_grants", {}).values():
            if g["subject_user_id"] != user_id:
                continue
            share = getattr(self, "_shares", {}).get(g["folder_id"])
            if (share and share["device_id"] == device_id
                    and not self._is_blocked(share["owner_id"], user_id)):
                out.append({"root_path": share["root_path"],
                            "permissions": g["permissions_granted"]})
        return out

    async def get_share(self, folder_id: str) -> dict | None:
        return getattr(self, "_shares", {}).get(folder_id)

    async def resolve_user(self, subject: str) -> str | None:
        try:
            return str(uuid.UUID(subject))
        except ValueError:
            return None

    # ── access requests + blocking ────────────────────────────────────────

    async def request_access(self, requester_id: str, folder_id: str, role: str) -> dict:
        share = getattr(self, "_shares", {}).get(folder_id)
        if not share:
            raise DeviceNotFound(folder_id)
        if share["owner_id"] == requester_id:
            raise GrantError("you own this folder")
        if role not in ("viewer", "editor", "manager"):
            raise GrantError("invalid role")
        if not hasattr(self, "_access_requests"):
            self._access_requests = {}
        for r in self._access_requests.values():
            if (r["folder_id"] == folder_id and r["requester_id"] == requester_id
                    and r["status"] == "pending"):
                raise GrantError("request already pending")
        req = {
            "id": str(uuid.uuid4()), "requester_id": requester_id,
            "folder_id": folder_id, "role": role, "status": "pending",
            "created_at": _now(), "resolved_at": None,
        }
        self._access_requests[req["id"]] = req
        return req

    async def list_access_requests(self, user_id: str, direction: str) -> list[dict]:
        out = []
        for r in getattr(self, "_access_requests", {}).values():
            share = getattr(self, "_shares", {}).get(r["folder_id"])
            if not share:
                continue
            if direction == "incoming" and share["owner_id"] != user_id:
                continue
            if direction == "outgoing" and r["requester_id"] != user_id:
                continue
            out.append({**r, "folder_label": share["label"],
                        "device_name": share["device_name"],
                        "owner_id": share["owner_id"],
                        "requester_email": None})
        return sorted(out, key=lambda r: r["created_at"], reverse=True)

    async def resolve_access_request(
        self, owner_id: str, request_id: str, approve: bool, permissions: int
    ) -> dict:
        req = getattr(self, "_access_requests", {}).get(request_id)
        if not req:
            raise DeviceNotFound(request_id)
        share = getattr(self, "_shares", {}).get(req["folder_id"])
        if not share or share["owner_id"] != owner_id:
            raise GrantError("only the folder owner can resolve requests")
        if req["status"] != "pending":
            raise GrantError("request already resolved")
        req["status"] = "approved" if approve else "denied"
        req["resolved_at"] = _now()
        if approve:
            await self.add_grant(req["folder_id"], req["requester_id"],
                                 permissions, owner_id)
        return req

    async def block_user(self, blocker_id: str, subject_id: str) -> None:
        if subject_id == blocker_id:
            raise GrantError("cannot block yourself")
        if not hasattr(self, "_blocked"):
            self._blocked = {}
        self._blocked.setdefault(blocker_id, set()).add(subject_id)

    async def unblock_user(self, blocker_id: str, subject_id: str) -> None:
        getattr(self, "_blocked", {}).get(blocker_id, set()).discard(subject_id)

    async def list_blocked(self, blocker_id: str) -> list[dict]:
        return [{"user_id": uid, "email": None}
                for uid in sorted(getattr(self, "_blocked", {}).get(blocker_id, set()))]
