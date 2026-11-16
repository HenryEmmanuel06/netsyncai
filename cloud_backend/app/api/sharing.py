"""Cross-user folder sharing.

Owner registers a shared folder rooted on one of their devices, then
grants permission bits to other users (resolved by uuid, email, or
@handle). Enforcement happens in api/files.py: non-owner requests need
the op's bit AND the path must be under a granted root. The agent still
applies its own root-level access flags on top.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import current_auth, get_device_store
from app.errors import http_403, http_404, http_422
from app.schemas.sharing import (
    GrantRequest,
    GrantResponse,
    SharedFolderResponse,
    SharesResponse,
    ShareCreateRequest,
)
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceNotFound, DeviceStore

router = APIRouter(prefix="/sharing", tags=["sharing"])


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
