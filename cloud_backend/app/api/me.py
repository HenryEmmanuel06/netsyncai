"""Personal tags, profile preferences, and search across all devices."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.api.deps import current_auth, get_device_store
from app.errors import http_404
from app.orchestration.dispatcher import (
    CommandFailed,
    CommandTimeout,
    DeviceOffline,
    dispatch,
)
from app.protocol import PERM_BROWSE
from app.security.jwt import AuthContext
from app.services.device_registry import DeviceNotFound, DeviceStore

log = logging.getLogger("netsync.me")

router = APIRouter(tags=["me"])

TAG_RE = r"^[A-Za-z0-9 _-]{1,40}$"


class TagRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    tag: str = Field(pattern=TAG_RE)


class PreferencesRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    discoverable: bool | None = None


# ── tags ─────────────────────────────────────────────────────────────────────

async def _has_access(user_id: str, device_id: str, path: str, store: DeviceStore):
    """Owner, or a collaborator with browse on a share covering path."""
    try:
        await store.get_device(user_id, device_id)
        return
    except DeviceNotFound:
        pass
    try:
        await store.get_device_by_id(device_id)
    except DeviceNotFound:
        raise http_404("device not found")
    bits = await store.effective_permissions(user_id, device_id, path)
    if not (bits & PERM_BROWSE):
        raise http_404("device not found")


@router.get("/devices/{device_id}/tags")
async def list_tags(
    device_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """{path: [tags]} for everything this user tagged on this device —
    caller merges into file listings client-side."""
    try:
        await store.get_device(auth.user_id, device_id)
    except DeviceNotFound:
        roots = [r for r in await store.granted_roots(auth.user_id, device_id)
                 if r["permissions"] & PERM_BROWSE]
        if not roots:
            raise http_404("device not found")
    return await store.list_tags(auth.user_id, device_id)


@router.put("/devices/{device_id}/tags", status_code=status.HTTP_201_CREATED)
async def add_tag(
    device_id: str,
    req: TagRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _has_access(auth.user_id, device_id, req.path, store)
    return await store.add_tag(auth.user_id, device_id, req.path, req.tag.strip())


@router.delete("/devices/{device_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(
    device_id: str,
    path: str,
    tag: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _has_access(auth.user_id, device_id, path, store)
    await store.remove_tag(auth.user_id, device_id, path, tag)


# ── profile preferences ──────────────────────────────────────────────────────

@router.get("/me/preferences")
async def get_preferences(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    prefs = await store.get_preferences(auth.user_id)
    return {**prefs, "email": auth.email, "user_id": auth.user_id}


@router.put("/me/preferences")
async def set_preferences(
    req: PreferencesRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return await store.set_preferences(auth.user_id, req.model_dump(exclude_none=True))


# ── search across all reachable devices ──────────────────────────────────────

async def _visible_devices(auth: AuthContext, store: DeviceStore) -> dict[str, dict]:
    """device_id -> {name, status, roots}. roots None = owner (all indexed roots)."""
    visible: dict[str, dict] = {}
    for d in await store.list_devices(auth.user_id):
        visible[d.id] = {"name": d.name, "status": d.status, "roots": None}
    for s in await store.list_shares_granted(auth.user_id):
        if not s["permissions"] & PERM_BROWSE:
            continue
        v = visible.get(s["device_id"])
        if v is None:
            try:
                dev = await store.get_device_by_id(s["device_id"])
                visible[s["device_id"]] = {
                    "name": s["device_name"], "status": dev.status, "roots": []}
            except DeviceNotFound:
                continue
            v = visible[s["device_id"]]
        if v["roots"] is not None:
            v["roots"].append(s["root_path"])
    return visible


def _norm_under(path: str, root: str) -> bool:
    p, r = path.replace("/", "\\").lower().rstrip("\\"), root.replace("/", "\\").lower().rstrip("\\")
    return p == r or p.startswith(r + "\\")


@router.get("/files/search-all")
async def search_all(
    q: str = Query(min_length=1, max_length=200),
    ext: str | None = None,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Fan out search_files to every online reachable device and merge."""
    visible = await _visible_devices(auth, store)

    async def one(device_id: str, meta: dict) -> dict:
        if meta["status"] != "online":
            return {"device_id": device_id, "device_name": meta["name"],
                    "status": meta["status"], "results": []}
        try:
            res = await dispatch(device_id, "search_files",
                                 {"query": q, "ext": ext}, timeout=20)
        except (DeviceOffline, CommandTimeout, CommandFailed):
            return {"device_id": device_id, "device_name": meta["name"],
                    "status": "offline", "results": []}
        results = res.get("results", [])
        if meta["roots"] is not None:
            results = [r for r in results
                       if any(_norm_under(r.get("path", ""), root)
                              for root in meta["roots"])]
        return {"device_id": device_id, "device_name": meta["name"],
                "status": "online", "results": results}

    per_device = await asyncio.gather(*[one(d, m) for d, m in visible.items()])
    total = sum(len(d["results"]) for d in per_device)
    return {"query": q, "total": total, "devices": per_device}
