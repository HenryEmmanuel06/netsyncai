"""Sync session management + event routing.

create → notifies both agents (start_sync with each one's own root).
Events then flow agent → coordinator → peer agent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import current_auth, get_device_store
from app.errors import http_404
from app.orchestration.dispatcher import CommandFailed, DeviceOffline, dispatch
from app.schemas.sync import SyncCreateRequest, SyncSessionResponse
from app.security.jwt import AuthContext
from app.services.device_registry import DeviceNotFound, DeviceStore

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("", response_model=SyncSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_sync(
    req: SyncCreateRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        await store.get_device(auth.user_id, req.a_device_id)
        await store.get_device(auth.user_id, req.b_device_id)
    except DeviceNotFound:
        raise http_404("device not found")

    session = await store.create_sync(
        auth.user_id, req.a_device_id, req.a_path,
        req.b_device_id, req.b_path, req.mode,
    )

    # start_sync on each agent with ITS OWN root; failures roll the session
    # back to error state rather than leaving a half-synced pair
    for device_id, root, peer in (
        (req.a_device_id, req.a_path, req.b_device_id),
        (req.b_device_id, req.b_path, req.a_device_id),
    ):
        try:
            await dispatch(device_id, "start_sync", {
                "session_id": session["id"],
                "root": root,
                "peer_device_id": peer,
                "mode": req.mode,
            }, timeout=15)
        except (DeviceOffline, CommandFailed) as exc:
            await store.set_sync_state(auth.user_id, session["id"], "error")
            session["state"] = "error"
            session["error"] = str(getattr(exc, "error", exc))
            break
    return session


@router.get("", response_model=list[SyncSessionResponse])
async def list_sync(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return await store.list_sync(auth.user_id)


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
    return session
