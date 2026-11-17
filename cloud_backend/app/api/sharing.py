"""Cross-user folder sharing.

Owner registers a shared folder rooted on one of their devices, then
grants permission bits to other users (resolved by uuid, email, or
@handle). Enforcement happens in api/files.py: non-owner requests need
the op's bit AND the path must be under a granted root. The agent still
applies its own root-level access flags on top.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from pydantic import BaseModel

from app.api.deps import current_auth, get_device_store
from app.errors import http_403, http_404, http_409, http_422
from app.orchestration.dispatcher import (
    CommandFailed,
    CommandTimeout,
    DeviceOffline,
    dispatch,
)
from app.schemas.sharing import (
    GrantRequest,
    GrantResponse,
    SharedFolderResponse,
    SharesResponse,
    ShareCreateRequest,
)
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceNotFound, DeviceStore, GrantError

router = APIRouter(prefix="/sharing", tags=["sharing"])

ROLE_BITS = {"viewer": 3, "editor": 255, "manager": 2047}
VIEWER_BITS = 1 | 2  # browse + download — the only bits safe on read-only roots


class AccessRequestBody(BaseModel):
    role: str = "viewer"            # role the requester is asking for


class BlockBody(BaseModel):
    subject: str                    # email / user id / @handle


def _map_store_errors(exc: Exception):
    if isinstance(exc, DeviceNotFound):
        return http_404("not found")
    return http_422(str(exc))


def _norm_path(p: str) -> str:
    return p.replace("/", "\\").rstrip("\\").lower()


async def _root_access(device_id: str, root_path: str) -> str | None:
    """Access level of the on-device shared root covering `root_path`.

    Returns None when it can't be verified (agent offline or root not
    registered) — the agent still enforces its own flags at op time, so
    unverifiable never means unsafe."""
    try:
        result = await dispatch(device_id, "list_folders", {}, timeout=15)
    except (DeviceOffline, CommandTimeout, CommandFailed):
        return None
    target = _norm_path(root_path)
    best_len, access = -1, None
    for f in result.get("folders") or []:
        fp = _norm_path(str(f.get("path") or ""))
        if fp and (target == fp or target.startswith(fp + "\\")) and len(fp) > best_len:
            best_len, access = len(fp), f.get("access")
    return access


async def _enforce_root_access(share: dict, permissions: int) -> None:
    """Roles beyond Viewer need the on-device root to allow writes."""
    if not permissions & ~VIEWER_BITS:
        return
    if await _root_access(share["device_id"], share["root_path"]) == "read":
        raise http_409(
            "this folder was shared with read-only access — set it to "
            "read & write on the device before granting Editor or Manager"
        )


@router.post("", response_model=SharedFolderResponse,
             status_code=status.HTTP_201_CREATED)
async def create_share(
    req: ShareCreateRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        await store.get_device(auth.user_id, req.device_id)
    except DeviceNotFound:
        raise http_404("device not found")
    share = await store.create_shared_folder(
        auth.user_id, req.device_id, req.label, req.root_path
    )
    await log_activity(store, auth.user_id, "share.created", device_id=req.device_id,
                       target=req.root_path, metadata={"label": share["label"]})
    return share


@router.get("", response_model=SharesResponse)
async def list_shares(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return SharesResponse(
        owned=await store.list_shares_owned(auth.user_id),
        granted=await store.list_shares_granted(auth.user_id),
    )


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share(
    folder_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    share = await store.get_share(folder_id)
    try:
        await store.delete_share(auth.user_id, folder_id)
    except DeviceNotFound:
        raise http_404("share not found")
    await log_activity(store, auth.user_id, "share.deleted",
                       device_id=share["device_id"] if share else None,
                       target=share["root_path"] if share else folder_id)


@router.post("/{folder_id}/grants", response_model=GrantResponse,
             status_code=status.HTTP_201_CREATED)
async def add_grant(
    folder_id: str,
    req: GrantRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    share = await store.get_share(folder_id)
    if not share:
        raise http_404("share not found")
    if share["owner_id"] != auth.user_id:
        raise http_403("only the folder owner can grant access")
    subject = await store.resolve_user(req.subject)
    if subject is None:
        raise http_422(f"cannot resolve user '{req.subject}'")
    if subject == auth.user_id:
        raise http_422("cannot grant access to yourself")
    await _enforce_root_access(share, req.permissions)
    try:
        grant = await store.add_grant(
            folder_id, subject, req.permissions, auth.user_id
        )
    except DeviceNotFound:
        raise http_404("share not found")
    await log_activity(store, auth.user_id, "grant.added",
                       device_id=share["device_id"], target=share["root_path"],
                       metadata={"subject": req.subject, "permissions": req.permissions})
    return grant


@router.get("/{folder_id}/grants", response_model=list[GrantResponse])
async def list_grants(
    folder_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    share = await store.get_share(folder_id)
    if not share or share["owner_id"] != auth.user_id:
        raise http_404("share not found")
    return await store.list_grants(folder_id)


@router.delete("/{folder_id}/grants/{grant_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def revoke_grant(
    folder_id: str,
    grant_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        await store.revoke_grant(folder_id, grant_id, auth.user_id)
    except DeviceNotFound:
        raise http_404("grant not found")
    await log_activity(store, auth.user_id, "grant.revoked", target=folder_id)


# ── access requests ────────────────────────────────────────────────────────────
# A granted user can request a role upgrade; the owner approves (creating the
# grant) or denies. Both directions are listed for the UI tabs.

@router.post("/{folder_id}/request", status_code=status.HTTP_201_CREATED)
async def request_access(
    folder_id: str,
    body: AccessRequestBody,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    share = await store.get_share(folder_id)
    if not share:
        raise http_404("share not found")
    try:
        req = await store.request_access(auth.user_id, folder_id, body.role)
    except (DeviceNotFound, GrantError) as exc:
        raise _map_store_errors(exc)
    await log_activity(store, auth.user_id, "share.access_requested",
                       device_id=share["device_id"], target=share["root_path"],
                       metadata={"role": body.role})
    return req


@router.get("/requests")
async def list_requests(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return {
        "incoming": await store.list_access_requests(auth.user_id, "incoming"),
        "outgoing": await store.list_access_requests(auth.user_id, "outgoing"),
    }


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    body: AccessRequestBody,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    incoming = await store.list_access_requests(auth.user_id, "incoming")
    match = next((r for r in incoming if r["id"] == request_id), None)
    if match:
        share = await store.get_share(match["folder_id"])
        if share:
            await _enforce_root_access(share, ROLE_BITS[body.role])
    try:
        req = await store.resolve_access_request(
            auth.user_id, request_id, True, ROLE_BITS[body.role])
    except (DeviceNotFound, GrantError) as exc:
        raise _map_store_errors(exc)
    await log_activity(store, auth.user_id, "grant.added", target=req["folder_id"],
                       metadata={"via": "access_request", "role": body.role})
    return req


@router.post("/requests/{request_id}/deny")
async def deny_request(
    request_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        req = await store.resolve_access_request(
            auth.user_id, request_id, False, 0)
    except (DeviceNotFound, GrantError) as exc:
        raise _map_store_errors(exc)
    await log_activity(store, auth.user_id, "share.access_denied", target=req["folder_id"])
    return req


# ── user blocking ─────────────────────────────────────────────────────────────
# An owner's block overrides every grant they've ever issued to that user
# (enforced inside effective_permissions / granted_roots on both stores).

@router.get("/blocks")
async def list_blocks(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return {"blocked": await store.list_blocked(auth.user_id)}


@router.post("/blocks", status_code=status.HTTP_201_CREATED)
async def block_user(
    body: BlockBody,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    subject = await store.resolve_user(body.subject)
    if subject is None:
        raise http_422(f"cannot resolve user '{body.subject}'")
    try:
        await store.block_user(auth.user_id, subject)
    except GrantError as exc:
        raise http_422(str(exc))
    await log_activity(store, auth.user_id, "user.blocked", metadata={"subject": body.subject})
    return {"blocked": subject}


@router.delete("/blocks/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(
    subject_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await store.unblock_user(auth.user_id, subject_id)
