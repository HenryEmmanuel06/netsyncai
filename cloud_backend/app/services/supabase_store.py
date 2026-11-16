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
        self._ensured: set[str] = set()
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

    async def ensure_profile(self, user_id: str, email: str) -> None:
        """Upsert the profiles row once per user — accounts created before
        the auth trigger existed would otherwise 409 on every FK'd write."""
        if user_id in self._ensured:
            return
        r = await self._client.post(
            "/profiles",
            headers={"Prefer": "return=minimal,resolution=merge-duplicates"},
            json={"id": user_id, "email": email},
        )
        r.raise_for_status()
        self._ensured.add(user_id)

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
        self, owner_id: str, device_name: str, ttl_seconds: int,
        owner_email: str | None = None,
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

    async def preview_pairing(self, code: str) -> dict:
        r = await self._client.get(
            "/device_pairing_requests",
            params={"code_hash": f"eq.{_hash(code.strip().upper())}",
                    "select": "device_name,expires_at,used_at,profiles(email)"},
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
        return {"device_name": rec["device_name"],
                "owner_email": (rec.get("profiles") or {}).get("email"),
                "expires_at": rec["expires_at"]}

    async def record_activity(
        self, actor_id: str | None, action: str, *, device_id: str | None = None,
        target: str | None = None, metadata: dict | None = None,
    ) -> None:
        r = await self._client.post(
            "/activity_logs",
            headers={"Prefer": "return=minimal"},
            json={"actor_id": actor_id, "device_id": device_id, "action": action,
                  "target": target, "metadata": metadata or {}},
        )
        r.raise_for_status()

    async def list_activity(self, actor_id: str, limit: int = 50) -> list[dict]:
        r = await self._client.get(
            "/activity_logs",
            params={"actor_id": f"eq.{actor_id}", "order": "created_at.desc",
                    "limit": limit},
        )
        r.raise_for_status()
        return r.json()

    # ── file tags + profile preferences ──

    async def add_tag(
        self, user_id: str, device_id: str, path: str, tag: str
    ) -> dict:
        r = await self._client.post(
            "/file_tags",
            headers={"Prefer": "return=representation,resolution=merge-duplicates"},
            json={"user_id": user_id, "device_id": device_id,
                  "path": path, "tag": tag},
        )
        r.raise_for_status()
        return {"path": path, "tag": tag}

    async def remove_tag(
        self, user_id: str, device_id: str, path: str, tag: str
    ) -> None:
        r = await self._client.delete(
            "/file_tags",
            params={"user_id": f"eq.{user_id}", "device_id": f"eq.{device_id}",
                    "path": f"eq.{path}", "tag": f"eq.{tag}"},
        )
        r.raise_for_status()

    async def list_tags(self, user_id: str, device_id: str) -> dict[str, list[str]]:
        r = await self._client.get(
            "/file_tags",
            params={"user_id": f"eq.{user_id}", "device_id": f"eq.{device_id}"},
        )
        r.raise_for_status()
        out: dict[str, list[str]] = {}
        for row in r.json():
            out.setdefault(row["path"], []).append(row["tag"])
        return {p: sorted(t) for p, t in out.items()}

    async def get_preferences(self, user_id: str) -> dict:
        r = await self._client.get(
            "/profiles", params={"id": f"eq.{user_id}",
                                 "select": "display_name,discoverable"},
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return {"display_name": "", "discoverable": True}
        return {"display_name": rows[0]["display_name"],
                "discoverable": rows[0]["discoverable"]}

    async def set_preferences(self, user_id: str, prefs: dict) -> dict:
        allowed = {k: v for k, v in prefs.items()
                   if k in ("display_name", "discoverable")}
        if allowed:
            r = await self._client.patch(
                "/profiles", params={"id": f"eq.{user_id}"}, json=allowed,
            )
            r.raise_for_status()
        return await self.get_preferences(user_id)

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

    # ── sync sessions ──

    async def create_sync(
        self, owner_id: str, a_device_id: str, a_path: str,
        b_device_id: str, b_path: str, mode: str,
    ) -> dict:
        r = await self._client.post(
            "/sync_sessions",
            json={
                "name": f"{a_path} ↔ {b_path}",
                "mode": mode, "state": "active", "created_by": owner_id,
            },
        )
        r.raise_for_status()
        session = r.json()[0]
        await self._client.post(
            "/sync_participants",
            json=[
                {"session_id": session["id"], "device_id": a_device_id, "root_path": a_path},
                {"session_id": session["id"], "device_id": b_device_id, "root_path": b_path},
            ],
        )
        session["participants"] = [
            {"device_id": a_device_id, "root": a_path},
            {"device_id": b_device_id, "root": b_path},
        ]
        return session

    def _sync_row(self, s: dict, participants: list[dict]) -> dict:
        return {
            **{k: v for k, v in s.items() if k != "sync_participants"},
            "participants": [
                {"device_id": p["device_id"], "root": p.get("root_path", "")}
                for p in participants
            ],
        }

    async def get_sync(self, session_id: str) -> dict:
        r = await self._client.get(
            "/sync_sessions",
            params={"id": f"eq.{session_id}", "select": "*,sync_participants(*)"},
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise DeviceNotFound(session_id)
        return self._sync_row(rows[0], rows[0].get("sync_participants", []))

    async def list_sync(self, owner_id: str) -> list[dict]:
        # sessions I created + sessions involving a device I own
        r = await self._client.get(
            "/sync_sessions",
            params={"created_by": f"eq.{owner_id}", "select": "*,sync_participants(*)"},
        )
        r.raise_for_status()
        sessions = {s["id"]: self._sync_row(s, s.get("sync_participants", []))
                    for s in r.json()}

        my_devices = await self.list_devices(owner_id)
        my_ids = ",".join(d.id for d in my_devices) or "00000000-0000-0000-0000-000000000000"
        r = await self._client.get(
            "/sync_participants",
            params={"device_id": f"in.({my_ids})",
                    "select": "device_id,root_path,sync_sessions(*,sync_participants(*))"},
        )
        r.raise_for_status()
        for row in r.json():
            s = row.get("sync_sessions")
            if s:
                sessions.setdefault(
                    s["id"], self._sync_row(s, s.get("sync_participants", []))
                )
        return list(sessions.values())

    async def _can_control_sync(self, actor_id: str, session: dict) -> bool:
        if session["created_by"] == actor_id:
            return True
        my_devices = {d.id for d in await self.list_devices(actor_id)}
        return any(p["device_id"] in my_devices for p in session["participants"])

    async def set_sync_state(self, actor_id: str, session_id: str, state: str) -> dict:
        session = await self.get_sync(session_id)
        if not await self._can_control_sync(actor_id, session):
            raise DeviceNotFound(session_id)
        r = await self._client.patch(
            "/sync_sessions",
            params={"id": f"eq.{session_id}"},
            json={"state": state, "updated_at": _now().isoformat()},
        )
        r.raise_for_status()
        session["state"] = state
        return session

    async def get_sync_participants(self, session_id: str) -> list[dict]:
        r = await self._client.get(
            "/sync_participants",
            params={"session_id": f"eq.{session_id}"},
        )
        r.raise_for_status()
        return [
            {"device_id": p["device_id"], "root": p.get("root_path", "")}
            for p in r.json()
        ]

    async def get_active_syncs_for_device(self, device_id: str) -> list[dict]:
        r = await self._client.get(
            "/sync_participants",
            params={
                "device_id": f"eq.{device_id}",
                "select": "root_path,session_id,sync_sessions(id,state,mode,sync_participants(device_id))",
            },
        )
        r.raise_for_status()
        out = []
        for row in r.json():
            s = row.get("sync_sessions") or {}
            if s.get("state") != "active":
                continue
            peer = next(
                (p["device_id"] for p in s.get("sync_participants", [])
                 if p["device_id"] != device_id), None,
            )
            if peer:
                out.append({
                    "session_id": row["session_id"], "root": row["root_path"],
                    "peer_device_id": peer, "mode": s["mode"],
                })
        return out

    # ── sharing & permissions ──

    async def create_shared_folder(
        self, owner_id: str, device_id: str, label: str, root_path: str
    ) -> dict:
        r = await self._client.post(
            "/shared_folders",
            json={"owner_id": owner_id, "device_id": device_id,
                  "label": label or root_path, "path_hint": root_path},
        )
        r.raise_for_status()
        row = r.json()[0]
        return self._share_row(row)

    def _share_row(self, row: dict) -> dict:
        return {
            "id": row["id"], "owner_id": row["owner_id"],
            "device_id": row["device_id"], "device_name": "",
            "label": row["label"], "root_path": row["path_hint"],
            "created_at": row["created_at"],
        }

    async def list_shares_owned(self, owner_id: str) -> list[dict]:
        r = await self._client.get(
            "/shared_folders",
            params={"owner_id": f"eq.{owner_id}",
                    "select": "*,devices(name)"},
        )
        r.raise_for_status()
        return [
            {**self._share_row(s), "device_name": (s.get("devices") or {}).get("name", "")}
            for s in r.json()
        ]

    async def list_shares_granted(self, user_id: str) -> list[dict]:
        r = await self._client.get(
            "/folder_permissions",
            params={
                "subject_user_id": f"eq.{user_id}",
                "select": "id,permissions_granted,folder_id,shared_folders(*,devices(name))",
            },
        )
        r.raise_for_status()
        out = []
        for g in r.json():
            s = g.get("shared_folders")
            if not s:
                continue
            out.append({
                **self._share_row(s),
                "device_name": (s.get("devices") or {}).get("name", ""),
                "permissions": g["permissions_granted"],
                "grant_id": g["id"],
            })
        return out

    async def add_grant(
        self, folder_id: str, subject_user_id: str, permissions: int, granted_by: str
    ) -> dict:
        role = "editor" if permissions > 3 else "viewer"
        r = await self._client.post(
            "/folder_permissions",
            json={
                "folder_id": folder_id, "subject_user_id": subject_user_id,
                "role": role, "permissions_granted": permissions,
                "granted_by": granted_by,
            },
        )
        r.raise_for_status()
        return r.json()[0]

    async def revoke_grant(self, folder_id: str, grant_id: str, owner_id: str) -> None:
        share = await self.get_share(folder_id)
        if not share or share["owner_id"] != owner_id:
            raise DeviceNotFound(grant_id)
        r = await self._client.delete(
            "/folder_permissions", params={"id": f"eq.{grant_id}"},
        )
        r.raise_for_status()

    async def list_grants(self, folder_id: str) -> list[dict]:
        r = await self._client.get(
            "/folder_permissions",
            params={"folder_id": f"eq.{folder_id}"},
        )
        r.raise_for_status()
        return r.json()

    async def delete_share(self, owner_id: str, folder_id: str) -> None:
        r = await self._client.delete(
            "/shared_folders",
            params={"id": f"eq.{folder_id}", "owner_id": f"eq.{owner_id}"},
        )
        r.raise_for_status()

    async def effective_permissions(
        self, user_id: str, device_id: str, path: str
    ) -> int:
        bits = 0
        norm = path.replace("/", "\\").lower().rstrip("\\")
        for g in await self.granted_roots(user_id, device_id):
            root = g["root_path"].replace("/", "\\").lower().rstrip("\\")
            if norm == root or norm.startswith(root + "\\"):
                bits |= g["permissions"]
        return bits

    async def granted_roots(self, user_id: str, device_id: str) -> list[dict]:
        # join grants to shares on this device
        r = await self._client.get(
            "/folder_permissions",
            params={
                "subject_user_id": f"eq.{user_id}",
                "select": "permissions_granted,shared_folders(device_id,path_hint)",
            },
        )
        r.raise_for_status()
        return [
            {"root_path": g["shared_folders"]["path_hint"],
             "permissions": g["permissions_granted"]}
            for g in r.json()
            if g.get("shared_folders") and g["shared_folders"]["device_id"] == device_id
        ]

    async def get_share(self, folder_id: str) -> dict | None:
        r = await self._client.get(
            "/shared_folders", params={"id": f"eq.{folder_id}"},
        )
        r.raise_for_status()
        rows = r.json()
        return self._share_row(rows[0]) if rows else None

    async def resolve_user(self, subject: str) -> str | None:
        # uuid → direct; else email or handle via profiles
        try:
            return str(uuid.UUID(subject))
        except ValueError:
            pass
        r = await self._client.get(
            "/profiles",
            params={
                "or": f"(email.eq.{subject},handle.eq.{subject.lstrip('@')})",
                "discoverable": "eq.true",  # opt-out hides email/handle lookup
                "select": "id",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0]["id"] if rows else None
