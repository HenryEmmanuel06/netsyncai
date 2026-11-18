"""Sync session management + event routing.

create → notifies both agents (start_sync with each one's own root).
Events then flow agent → coordinator → peer agent.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, status

from app.api.deps import current_auth, get_device_store
from app.errors import http_404, http_409, http_422
from app.protocol import PERM_START_SYNC
from app.orchestration.dispatcher import CommandFailed, DeviceOffline, dispatch
from app.schemas.sync import (
    SyncAcceptRequest, SyncCreateRequest, SyncSessionResponse,
)
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceNotFound, DeviceStore

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("", response_model=SyncSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_sync(
    req: SyncCreateRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    # request addressed to a colleague by email/handle/id — they pick their
    # destination folder when they accept; the session stays 'pending'.
    if req.b_user:
        target = await store.resolve_user(req.b_user)
        if target is None:
            raise http_422("no account matches that email or handle")
        if target == auth.user_id:
            raise http_409("that's your own account — choose one of your computers")
        try:
            await store.get_device(auth.user_id, req.a_device_id)
        except DeviceNotFound:
            raise http_404("device not found")
        session = await store.create_sync(
            auth.user_id, req.a_device_id, req.a_path, None, None, req.mode,
            state="pending", pending_user_id=target,
        )
        await log_activity(store, auth.user_id, "sync.requested",
                           target=session["name"],
                           metadata={"to": req.b_user})
        return session

    if not req.b_device_id or not req.b_path:
        raise http_422("choose a folder on each side, or enter a colleague's email")

    owned = 0
    for device_id, path in ((req.a_device_id, req.a_path), (req.b_device_id, req.b_path)):
        try:
            await store.get_device(auth.user_id, device_id)
            owned += 1
            continue
        except DeviceNotFound:
            pass
        # colleague's device: need a share covering the path with start_sync
        bits = await store.effective_permissions(auth.user_id, device_id, path)
        if not bits or not (bits & PERM_START_SYNC):
            raise http_404("device not found")
    if owned == 0:
        raise http_404("device not found")

    # sessions involving someone else's computer need their acceptance —
    # created 'pending'; the other side's dashboard shows an accept/decline
    # request and only then do the agents start.
    needs_accept = owned < 2
    session = await store.create_sync(
        auth.user_id, req.a_device_id, req.a_path,
        req.b_device_id, req.b_path, req.mode,
        state="pending" if needs_accept else "active",
    )

    if needs_accept:
        await log_activity(store, auth.user_id, "sync.requested",
                           target=session["name"])
        return session

    await _start_agents(session, req.mode, auth.user_id, store)
    await log_activity(store, auth.user_id, "sync.started", target=session["name"],
                       metadata={"state": session["state"], "mode": req.mode})
    return session


async def _start_agents(
    session: dict, mode: str, actor_id: str, store: DeviceStore
) -> None:
    """Dispatch start_sync to each participant agent with ITS OWN root."""
    if len(session["participants"]) < 2:
        return
    for p in session["participants"]:
        peer = next(q["device_id"] for q in session["participants"]
                    if q["device_id"] != p["device_id"])
        try:
            await dispatch(p["device_id"], "start_sync", {
                "session_id": session["id"],
                "root": p["root"],
                "peer_device_id": peer,
                "mode": mode,
            }, timeout=15)
        except (DeviceOffline, CommandFailed) as exc:
            await store.set_sync_state(actor_id, session["id"], "error")
            session["state"] = "error"
            session["error"] = str(getattr(exc, "error", exc))
            break


def _safe_folder_name(raw: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", raw).strip(" .")
    return name or "NetSync Folder"


async def _downloads_root(session: dict, device_id: str) -> str:
    """`Downloads\\<source folder name>` on the accepter's PC — the agent
    creates and registers it readwrite so start_sync can write there."""
    try:
        dirs = await dispatch(device_id, "list_local_dirs", {}, timeout=15)
    except (DeviceOffline, CommandFailed) as exc:
        raise http_409(str(getattr(exc, "error", exc)))
    dl = next((e["path"] for e in dirs.get("entries", [])
               if e.get("name") == "Downloads"), None)
    if not dl:
        raise http_409("couldn't locate a Downloads folder — pick one instead")
    src = ""
    if session["participants"]:
        src = (session["participants"][0]["root"].rstrip("\\/")
               .replace("/", "\\").split("\\")[-1])
    name = _safe_folder_name(src or session["name"])
    target = dl.rstrip("\\") + "\\" + name
    try:
        # unique: a second colleague's "methic" must not merge into the
        # first one's Downloads\methic — the agent picks methic (2), (3)…
        res = await dispatch(device_id, "add_folder",
                             {"path": target, "access": "readwrite",
                              "create": True, "unique": True}, timeout=15)
    except (DeviceOffline, CommandFailed) as exc:
        raise http_409(str(getattr(exc, "error", exc)))
    return res.get("path", target)


@router.get("/requests")
async def sync_requests(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Pending sessions that need MY acceptance — I own a participant
    device but didn't create the session, or it was addressed to me."""
    out = []
    for s in await store.list_sync(auth.user_id):
        if s["state"] != "pending" or s["created_by"] == auth.user_id:
            continue
        if s.get("pending_user_id") == auth.user_id:
            out.append({**s, "needs_folder": True})
            continue
        for p in s["participants"]:
            try:
                dev = await store.get_device(auth.user_id, p["device_id"])
                out.append({**s, "my_device_name": dev.name, "my_root": p["root"]})
                break
            except DeviceNotFound:
                continue
    return {"requests": out}


@router.post("/{session_id}/accept", response_model=SyncSessionResponse)
async def accept_sync(
    session_id: str,
    body: SyncAcceptRequest | None = None,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        session = await store.get_sync(session_id)
    except DeviceNotFound:
        raise http_404("sync session not found")
    if session.get("pending_user_id"):
        # request addressed to me: I choose which of my folders receives it
        if session["pending_user_id"] != auth.user_id:
            raise http_404("sync session not found")
        if body is None:
            raise http_422("choose a folder on your computer to sync into")
        try:
            await store.get_device(auth.user_id, body.device_id)
        except DeviceNotFound:
            raise http_404("device not found")
        if body.to_downloads:
            root_path = await _downloads_root(session, body.device_id)
        elif body.root_path:
            root_path = body.root_path
        else:
            raise http_422("choose a folder on your computer to sync into")
        session = await store.add_sync_participant(
            session_id, body.device_id, root_path)
    try:
        session = await store.set_sync_state(auth.user_id, session_id, "active")
    except DeviceNotFound:
        raise http_404("sync session not found")
    await _start_agents(session, session.get("mode", "live"), auth.user_id, store)
    await log_activity(store, auth.user_id, "sync.accepted", target=session["name"])
    return session


@router.post("/{session_id}/decline", response_model=SyncSessionResponse)
async def decline_sync(
    session_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        session = await store.set_sync_state(auth.user_id, session_id, "stopped")
    except DeviceNotFound:
        raise http_404("sync session not found")
    await log_activity(store, auth.user_id, "sync.declined", target=session["name"])
    return session


@router.get("", response_model=list[SyncSessionResponse])
async def list_sync(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return await store.list_sync(auth.user_id)


@router.get("/{session_id}/live")
async def sync_live(
    session_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Live per-side counters from the agents' sync engines — applied /
    emitted / pending ops, merged across both participants."""
    sessions = await store.list_sync(auth.user_id)
    session = next((s for s in sessions if s["id"] == session_id), None)
    if session is None:
        raise http_404("sync session not found")
    sides = []
    for p in session["participants"]:
        side = {"device_id": p["device_id"], "root": p["root"], "online": False,
                "gone": False, "name": "", "applied_ops": 0, "emitted_ops": 0,
                "pending_ops": 0, "paused": False, "transfers": []}
        try:
            dev = await store.get_device_by_id(p["device_id"])
            side["name"] = dev.name
            side["gone"] = dev.revoked_at is not None
        except DeviceNotFound:
            side["gone"] = True
            side["name"] = "removed device"
        if side["gone"]:
            sides.append(side)  # a dead device can never report in
            continue
        try:
            res = await dispatch(p["device_id"], "get_device_status", {}, timeout=10)
            sess = (res.get("sync_sessions") or {}).get(session_id)
            if sess:
                side.update({k: sess.get(k, side[k]) for k in
                             ("applied_ops", "emitted_ops", "pending_ops", "paused")})
                side["online"] = True
            side["transfers"] = res.get("transfers", [])
        except Exception:
            pass
        sides.append(side)
    return {"session_id": session_id, "sides": sides,
            "applied_ops": sum(s["applied_ops"] for s in sides),
            "pending_ops": sum(s["pending_ops"] for s in sides)}


@router.post("/{session_id}/{action}", response_model=SyncSessionResponse)
async def sync_action(
    session_id: str,
    action: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    if action not in ("pause", "resume", "stop"):
        raise http_404("unknown action")
    try:
        session = await store.set_sync_state(
            auth.user_id, session_id,
            {"pause": "paused", "resume": "active", "stop": "stopped"}[action],
        )
    except DeviceNotFound:
        raise http_404("sync session not found")

    tool = f"{action}_sync" if action != "stop" else "stop_sync"
    for p in session["participants"]:
        try:
            await dispatch(p["device_id"], tool, {"session_id": session_id}, timeout=10)
        except (DeviceOffline, CommandFailed):
            pass  # agent applies on reconnect; state is authoritative
    await log_activity(store, auth.user_id, f"sync.{action}", target=session["name"])
    return session
