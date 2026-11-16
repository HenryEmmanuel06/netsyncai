"""Shared-folder management for the device OWNER, from the dashboard.

Replaces `netsync-agent index <folder> --access …`. Every route requires
device ownership (collaborators get 404); the agent additionally refuses
system/credential locations no matter who asks.
"""

from __future__ import annotations

import functools
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import current_auth, get_device_store
from app.errors import http_404, http_409
from app.orchestration.dispatcher import (
    CommandFailed,
    CommandTimeout,
    DeviceOffline,
    dispatch,
)
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceNotFound, DeviceStore

router = APIRouter(prefix="/devices/{device_id}", tags=["folders"])


class AddFolderRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    access: Literal["read", "readwrite"] = "read"
    label: str = Field(default="", max_length=120)


class FolderAccessRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    access: Literal["read", "readwrite"]


class FolderPathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)


def _agent_errors(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except DeviceOffline:
            raise http_409("device is offline — open NetSync AI on that computer")
        except CommandTimeout:
            raise http_409("the computer did not respond in time")
        except CommandFailed as exc:
            raise http_409(exc.error)
    return wrapper


async def _owner(device_id: str, auth: AuthContext, store: DeviceStore):
    try:
        return await store.get_device(auth.user_id, device_id)
    except DeviceNotFound:
        raise http_404("device not found")


@router.get("/local-dirs")
@_agent_errors
async def local_dirs(
    device_id: str,
    path: str = "",
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Directory picker: drives/quick locations, then subfolders. Folder
    names only — never files."""
    await _owner(device_id, auth, store)
    return await dispatch(device_id, "list_local_dirs", {"path": path})


@router.get("/folders")
@_agent_errors
async def list_folders(
    device_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _owner(device_id, auth, store)
    return await dispatch(device_id, "list_folders", {})


@router.post("/folders", status_code=201)
@_agent_errors
async def add_folder(
    device_id: str,
    req: AddFolderRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    dev = await _owner(device_id, auth, store)
    result = await dispatch(device_id, "add_folder", req.model_dump())
    await log_activity(store, auth.user_id, "folder.added", device_id=device_id,
                       target=result.get("path"),
                       metadata={"access": req.access, "device": dev.name})
    return result


@router.patch("/folders")
@_agent_errors
async def set_folder_access(
    device_id: str,
    req: FolderAccessRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _owner(device_id, auth, store)
    result = await dispatch(device_id, "set_folder_access", req.model_dump())
    await log_activity(store, auth.user_id, "folder.access_changed",
                       device_id=device_id, target=req.path,
                       metadata={"access": req.access})
    return result


@router.post("/folders/remove")
@_agent_errors
async def remove_folder(
    device_id: str,
    req: FolderPathRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _owner(device_id, auth, store)
    result = await dispatch(device_id, "remove_folder", req.model_dump())
    await log_activity(store, auth.user_id, "folder.removed",
                       device_id=device_id, target=req.path)
    return result


@router.post("/folders/reindex")
@_agent_errors
async def reindex_folder(
    device_id: str,
    req: FolderPathRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _owner(device_id, auth, store)
    return await dispatch(device_id, "reindex_folder", req.model_dump(), timeout=300)
