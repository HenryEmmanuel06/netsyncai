"""Sync session management + event routing.

create → notifies both agents (start_sync with each one's own root).
Events then flow agent → coordinator → peer agent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import current_auth, get_device_store
from app.errors import http_404
from app.protocol import PERM_START_SYNC
from app.orchestration.dispatcher import CommandFailed, DeviceOffline, dispatch
from app.schemas.sync import SyncCreateRequest, SyncSessionResponse
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


@router.get("/requests")
async def sync_requests(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Pending sessions that need MY acceptance — I own a participant
    device but didn't create the session."""
    out = []
    for s in await store.list_sync(auth.user_id):
        if s["state"] != "pending" or s["created_by"] == auth.user_id:
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
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
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
                "applied_ops": 0, "emitted_ops": 0, "pending_ops": 0, "paused": False}
        try:
            res = await dispatch(p["device_id"], "get_device_status", {}, timeout=10)
            sess = (res.get("sync_sessions") or {}).get(session_id)
            if sess:
                side.update({k: sess.get(k, side[k]) for k in
                             ("applied_ops", "emitted_ops", "pending_ops", "paused")})
                side["online"] = True
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
