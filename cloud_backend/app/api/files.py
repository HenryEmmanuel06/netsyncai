"""Remote file operations — REST façade over agent command dispatch.

Every route: verify the caller owns the device → dispatch tool command →
the agent enforces its own local permissions/path security. Downloads and
uploads stream base64 chunks over the agent's existing WSS connection
(relay transport; direct LAN P2P plugs into the same envelope later).
"""

from __future__ import annotations

import functools
import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import current_auth, get_device_store
from app.errors import http_404, http_409
from app.protocol import (
    PERM_BROWSE, PERM_CREATE_FOLDER, PERM_DELETE, PERM_DOWNLOAD,
    PERM_MOVE, PERM_RENAME, PERM_UPLOAD,
)
from app.networking import transfers
from app.networking.connections import manager
from app.orchestration import dispatcher
from app.orchestration.dispatcher import (
    CommandFailed,
    CommandTimeout,
    DeviceOffline,
    dispatch,
)
from app.protocol import Envelope, MessageType, TransferBegin, TransferEnd
from app.schemas.devices import DeviceResponse
from app.schemas.files import (
    BrowseResponse,
    MkdirRequest,
    MoveCopyRequest,
    PathRequest,
    RenameRequest,
    SearchResponse,
)
from app.security.jwt import AuthContext
from app.services.activity import log_activity
from app.services.device_registry import DeviceNotFound, DeviceStore

log = logging.getLogger("netsync.files")
router = APIRouter(prefix="/devices/{device_id}", tags=["files"])

TRANSFER_TIMEOUT = 300.0


async def _owned_device(
    device_id: str, auth: AuthContext, store: DeviceStore
) -> DeviceResponse:
    try:
        return await store.get_device(auth.user_id, device_id)
    except DeviceNotFound:
        raise http_404("device not found")


async def _authorize(
    device_id: str, auth: AuthContext, store: DeviceStore,
    path: str, required_bit: int,
) -> tuple[DeviceResponse, bool]:
    """Owner → (device, True). Collaborator → (device, False) iff a grant
    on a shared folder covering `path` includes required_bit. Denials are
    404s — device existence is not leaked."""
    try:
        return await store.get_device(auth.user_id, device_id), True
    except DeviceNotFound:
        pass
    try:
        dev = await store.get_device_by_id(device_id)
    except DeviceNotFound:
        raise http_404("device not found")
    bits = await store.effective_permissions(auth.user_id, device_id, path)
    if not bits or not (bits & required_bit):
        raise http_404("device not found")
    return dev, False


def _under_roots(path: str, roots: list[dict]) -> bool:
    norm = path.replace("/", "\\").lower().rstrip("\\")
    for r in roots:
        root = r["root_path"].replace("/", "\\").lower().rstrip("\\")
        if norm == root or norm.startswith(root + "\\"):
            return True
    return False


def _map_errors(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except DeviceOffline:
            raise http_409("device is offline")
        except CommandTimeout:
            raise http_409("agent did not respond in time")
        except CommandFailed as exc:
            raise http_409(exc.error)
    return wrapper


@router.get("/browse", response_model=BrowseResponse)
@_map_errors
async def browse(
    device_id: str,
    path: str = "",
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    if not path:
        # roots listing: owners see all; collaborators see only granted roots
        try:
            await store.get_device(auth.user_id, device_id)
            is_owner = True
        except DeviceNotFound:
            is_owner = False
        if is_owner:
            result = await dispatch(device_id, "browse_folder", {"path": ""})
        else:
            roots = await store.granted_roots(auth.user_id, device_id)
            roots = [r for r in roots if r["permissions"] & PERM_BROWSE]
            if not roots:
                raise http_404("device not found")
            return BrowseResponse(path="", entries=[], roots=[
                {"id": 0, "path": r["root_path"], "label": "shared",
                 "access": "granted"} for r in roots
            ])
    else:
        await _authorize(device_id, auth, store, path, PERM_BROWSE)
        result = await dispatch(device_id, "browse_folder", {"path": path})
    return BrowseResponse(
        path=path,
        entries=result.get("entries", []),
        roots=result.get("roots"),
    )


@router.get("/stats")
@_map_errors
async def device_stats(
    device_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Owner-only local stats — disk free on indexed drives, agent
    version, LibreOffice availability."""
    await _owned_device(device_id, auth, store)
    return await dispatch(device_id, "sys_info", {})


@router.post("/convert")
@_map_errors
async def convert_document(
    device_id: str,
    body: PathRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Ask the agent to convert a document to PDF (LibreOffice headless).
    Writes a sibling .pdf — requires upload-level permission."""
    await _authorize(device_id, auth, store, body.path, PERM_UPLOAD)
    result = await dispatch(device_id, "convert_document",
                            {"path": body.path, "to": "pdf"})
    await log_activity(store, auth.user_id, "file.converted",
                       device_id=device_id, target=body.path)
    return result


@router.get("/search", response_model=SearchResponse)
@_map_errors
async def search(
    device_id: str,
    q: str = "",
    ext: str | None = None,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    try:
        await store.get_device(auth.user_id, device_id)
        allowed_roots = None
    except DeviceNotFound:
        allowed_roots = [
            r for r in await store.granted_roots(auth.user_id, device_id)
            if r["permissions"] & PERM_BROWSE
        ]
        if not allowed_roots:
            raise http_404("device not found")
    result = await dispatch(
        device_id, "search_files", {"query": q, "ext": ext}
    )
    results = result.get("results", [])
    if allowed_roots is not None:
        results = [
            r for r in results
            if _under_roots(r.get("path", ""), allowed_roots)
        ]
    return SearchResponse(query=q, results=results)


@router.post("/rename")
@_map_errors
async def rename(
    device_id: str,
    req: RenameRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _authorize(device_id, auth, store, req.path, PERM_RENAME)
    result = await dispatch(
        device_id, "rename_file",
        {"path": req.path, "new_name": req.new_name},
    )
    await log_activity(store, auth.user_id, "file.renamed", device_id=device_id,
                       target=req.path, metadata={"new_name": req.new_name})
    return result


@router.post("/move")
@_map_errors
async def move(
    device_id: str,
    req: MoveCopyRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _authorize(device_id, auth, store, req.src, PERM_MOVE)
    await _authorize(device_id, auth, store, req.dst, PERM_MOVE)
    result = await dispatch(
        device_id, "move_file", {"src": req.src, "dst": req.dst}
    )
    await log_activity(store, auth.user_id, "file.moved", device_id=device_id,
                       target=req.src, metadata={"to": req.dst})
    return result


@router.post("/copy")
@_map_errors
async def copy(
    device_id: str,
    req: MoveCopyRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _authorize(device_id, auth, store, req.src, PERM_DOWNLOAD)
    await _authorize(device_id, auth, store, req.dst, PERM_UPLOAD)
    result = await dispatch(
        device_id, "copy_file", {"src": req.src, "dst": req.dst}
    )
    await log_activity(store, auth.user_id, "file.copied", device_id=device_id,
                       target=req.src, metadata={"to": req.dst})
    return result


@router.post("/mkdir")
@_map_errors
async def mkdir(
    device_id: str,
    req: MkdirRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _authorize(device_id, auth, store, req.path, PERM_CREATE_FOLDER)
    result = await dispatch(device_id, "create_folder", {"path": req.path})
    await log_activity(store, auth.user_id, "file.folder_created",
                       device_id=device_id, target=req.path)
    return result


@router.delete("/file")
@_map_errors
async def delete(
    device_id: str,
    path: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    await _authorize(device_id, auth, store, path, PERM_DELETE)
    result = await dispatch(device_id, "delete_file", {"path": path})
    await log_activity(store, auth.user_id, "file.deleted",
                       device_id=device_id, target=path)
    return result


# ── transfers ────────────────────────────────────────────────────────────────

@router.get("/download")
@_map_errors
async def download(
    device_id: str,
    path: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Agent → relay → browser. Agent sends TRANSFER_BEGIN/CHUNK/END; we
    stream to the client and verify the SHA-256 announced in BEGIN."""
    await _authorize(device_id, auth, store, path, PERM_DOWNLOAD)
    await log_activity(store, auth.user_id, "file.downloaded",
                       device_id=device_id, target=path)
    transfer_id = str(uuid.uuid4())
    queue = transfers.register(transfer_id)

    # dispatch in background; the agent streams into `queue`
    import asyncio
    dispatch_task = asyncio.create_task(
        dispatch(device_id, "download_file",
                 {"path": path, "transfer_id": transfer_id},
                 timeout=TRANSFER_TIMEOUT)
    )

    return await _download_response(queue, dispatch_task, transfer_id)


async def _download_response(queue, dispatch_task, transfer_id):
    """Wait for TRANSFER_BEGIN so we can set filename/size headers."""
    import asyncio
    first: Envelope = await asyncio.wait_for(queue.get(), timeout=30)
    if first.type is not MessageType.TRANSFER_BEGIN:
        transfers.unregister(transfer_id)
        raise CommandFailed("agent did not begin transfer")
    begin = TransferBegin.model_validate(first.payload)
    hasher = hashlib.sha256()

    async def body():
        try:
            while True:
                env = await asyncio.wait_for(queue.get(), timeout=TRANSFER_TIMEOUT)
                if env.type is MessageType.TRANSFER_CHUNK:
                    data = transfers.decode_chunk(env)
                    hasher.update(data)
                    yield data
                elif env.type is MessageType.TRANSFER_END:
                    if hasher.hexdigest() != begin.sha256:
                        raise CommandFailed("sha256 mismatch")
                    break
                elif env.type is MessageType.TRANSFER_ABORT:
                    raise CommandFailed(env.payload.get("reason", "aborted"))
        finally:
            transfers.unregister(transfer_id)
            await dispatch_task

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{begin.name}"',
            "X-Content-Sha256": begin.sha256,
            "X-Content-Size": str(begin.size),
        },
    )


@router.post("/upload")
@_map_errors
async def upload(
    device_id: str,
    path: str,
    file: UploadFile,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    """Browser → relay → agent. Chunks the upload body over the WSS; the
    agent writes to a partial file, verifies, and atomically renames."""
    await _authorize(device_id, auth, store, path, PERM_UPLOAD)
    transfer_id = str(uuid.uuid4())
    hasher = hashlib.sha256()

    # 1. command first — the agent registers the pending write + dest path
    step_id = await dispatcher.send_command(
        device_id, "send_file",
        {"path": path, "transfer_id": transfer_id},
    )

    # 2. then stream the payload
    await manager.send(device_id, Envelope(
        type=MessageType.TRANSFER_BEGIN,
        payload=TransferBegin(
            transfer_id=transfer_id, direction="push",
            name=file.filename or "upload", size=0, sha256="",
        ).model_dump(),
    ).model_dump_json())

    seq = 0
    total = 0
    while chunk := await file.read(transfers.CHUNK_SIZE):
        hasher.update(chunk)
        total += len(chunk)
        await manager.send(
            device_id,
            transfers.chunk_envelope(transfer_id, seq, chunk).model_dump_json(),
        )
        seq += 1

    digest = hasher.hexdigest()
    await manager.send(device_id, Envelope(
        type=MessageType.TRANSFER_END,
        payload=TransferEnd(transfer_id=transfer_id, seq=seq, sha256=digest).model_dump(),
    ).model_dump_json())

    # 3. agent verifies sha256 + atomically renames, then returns result
    result = await dispatcher.await_result(step_id, timeout=TRANSFER_TIMEOUT)
    await log_activity(store, auth.user_id, "file.uploaded", device_id=device_id,
                       target=result.get("written", path), metadata={"size": total})
    return result
