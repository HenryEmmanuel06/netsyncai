"""Remote file-operation handlers — the agent's local command engine.

Every remote command lands here. The agent is the FINAL authority:
- paths must resolve under a registered root (PathSecurityError otherwise)
- the containing folder's `access` level decides read vs write ops
- destructive ops are denied outright on read-only folders
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from indexing.indexer import index_folder, search_files
from security.paths import AllowedRoots, PathSecurityError

log = logging.getLogger("netsync.ops")

READ_OPS = {"browse_folder", "search_files", "download_file"}
WRITE_OPS = {
    "rename_file", "move_file", "copy_file", "delete_file",
    "create_folder", "send_file",
}

CHUNK = 64 * 1024
PARTIAL_DIR = ".netsync-partial"


class OpDenied(Exception):
    """Permission or path denial — reported to the coordinator as a failed
    command result, never as a crash."""


@dataclass
class IncomingTransfer:
    transfer_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    dest: Path | None = None


class AgentContext:
    """Per-connection state shared by all op handlers."""

    def __init__(self, conn: sqlite3.Connection, send: Callable[[str], Awaitable[None]]):
        self.conn = conn
        self.send = send
        self.incoming: dict[str, IncomingTransfer] = {}

    def roots_for(self, write: bool) -> AllowedRoots:
        """Allowed roots = registered folders with sufficient access."""
        level = ("read", "readwrite") if not write else ("readwrite",)
        rows = self.conn.execute(
            f"SELECT path FROM indexed_folders WHERE access IN ({','.join('?'*len(level))})",
            level,
        ).fetchall()
        roots = AllowedRoots()
        for r in rows:
            try:
                roots.add(r["path"])
            except PathSecurityError:
                continue
        return roots

    def check_path(self, raw: str, write: bool = False) -> Path:
        roots = self.roots_for(write)
        try:
            return roots.safe_resolve(raw)
        except PathSecurityError as exc:
            raise OpDenied(str(exc)) from exc

    def transfer_state(self, transfer_id: str) -> IncomingTransfer:
        return self.incoming.setdefault(
            transfer_id, IncomingTransfer(transfer_id)
        )


# ── read ops ─────────────────────────────────────────────────────────────────

async def op_browse_folder(ctx: AgentContext, args: dict) -> dict:
    path = args.get("path", "")
    if not path:
        rows = ctx.conn.execute(
            "SELECT id, path, label, access FROM indexed_folders WHERE access != 'none'"
        ).fetchall()
        return {
            "roots": [
                {"id": r["id"], "path": r["path"], "label": r["label"], "access": r["access"]}
                for r in rows
            ],
            "entries": [],
        }
    target = ctx.check_path(path)
    if not target.is_dir():
        raise OpDenied("not a directory")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            st = child.stat()
        except OSError:
            continue
        entries.append({
            "name": child.name,
            "rel_path": str(child),
            "is_dir": child.is_dir(),
            "ext": child.suffix.lower() if child.is_file() else None,
            "size": None if child.is_dir() else st.st_size,
            "mtime": st.st_mtime,
        })
    return {"entries": entries, "roots": None}


async def op_search_files(ctx: AgentContext, args: dict) -> dict:
    return {
        "results": search_files(
            ctx.conn,
            args.get("query", ""),
            ext=args.get("ext"),
            limit=args.get("limit", 50),
        )
    }


async def op_download_file(ctx: AgentContext, args: dict) -> dict:
    from protocol import Envelope, MessageType, TransferBegin, TransferChunk, TransferEnd

    transfer_id = args["transfer_id"]
    path = ctx.check_path(args["path"])
    if not path.is_file():
        raise OpDenied("not a file")

    # pre-hash so BEGIN announces the real digest (verified by receiver)
    size = path.stat().st_size
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    digest = h.hexdigest()

    await ctx.send(Envelope(
        type=MessageType.TRANSFER_BEGIN,
        payload=TransferBegin(
            transfer_id=transfer_id, direction="pull",
            name=path.name, size=size, sha256=digest,
        ).model_dump(),
    ).model_dump_json())

    seq = 0
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
            await ctx.send(Envelope(
                type=MessageType.TRANSFER_CHUNK,
                payload=TransferChunk(
                    transfer_id=transfer_id, seq=seq,
                    data=base64.b64encode(chunk).decode(),
                ).model_dump(),
            ).model_dump_json())
            seq += 1
    await ctx.send(Envelope(
        type=MessageType.TRANSFER_END,
        payload=TransferEnd(transfer_id=transfer_id, seq=seq, sha256=digest).model_dump(),
    ).model_dump_json())
    return {"transfer_id": transfer_id, "size": size, "sha256": digest}


# ── write ops ────────────────────────────────────────────────────────────────

async def op_rename_file(ctx: AgentContext, args: dict) -> dict:
    src = ctx.check_path(args["path"], write=True)
    new_name = args["new_name"]
    if "/" in new_name or "\\" in new_name or new_name in (".", ".."):
        raise OpDenied("invalid new_name")
    dst = src.with_name(new_name)
    if not src.exists():
        raise OpDenied("source does not exist")
    os.rename(src, dst)
    _update_index_path(ctx, src, dst)
    return {"renamed": str(dst)}


async def op_move_file(ctx: AgentContext, args: dict) -> dict:
    src = ctx.check_path(args["src"], write=True)
    dst = ctx.check_path(args["dst"], write=True)
    if dst.is_dir():
        dst = dst / src.name
    shutil.move(str(src), str(dst))
    _update_index_path(ctx, src, dst)
    return {"moved": str(dst)}


async def op_copy_file(ctx: AgentContext, args: dict) -> dict:
    src = ctx.check_path(args["src"], write=True)
    dst = ctx.check_path(args["dst"], write=True)
    if dst.is_dir():
        dst = dst / src.name
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return {"copied": str(dst)}


async def op_delete_file(ctx: AgentContext, args: dict) -> dict:
    target = ctx.check_path(args["path"], write=True)
    if target.is_dir():
        target.rmdir()  # empty dirs only — no recursive delete remotely
    else:
        target.unlink()
    ctx.conn.execute(
        "UPDATE files SET deleted = 1 WHERE rel_path = ? OR name = ?",
        (str(target), target.name),
    )
    ctx.conn.commit()
    return {"deleted": str(target)}


async def op_create_folder(ctx: AgentContext, args: dict) -> dict:
    target = ctx.check_path(args["path"], write=True)
    target.mkdir(parents=True, exist_ok=True)
    return {"created": str(target)}


async def op_send_file(ctx: AgentContext, args: dict) -> dict:
    """Receive a push transfer: dest path + chunks via incoming queue."""
    dest = ctx.check_path(args["path"], write=True)
    if dest.is_dir():
        dest = dest / args.get("name", "upload")
    transfer_id = args["transfer_id"]
    state = ctx.transfer_state(transfer_id)
    state.dest = dest

    tmp_dir = dest.parent / PARTIAL_DIR
    tmp_dir.mkdir(exist_ok=True)
    tmp = tmp_dir / f"{transfer_id}.part"

    h = hashlib.sha256()
    received_end: dict | None = None
    try:
        with tmp.open("wb") as f:
            while True:
                env = await asyncio.wait_for(state.queue.get(), timeout=300)
                if env.type.value == "transfer.chunk":
                    data = base64.b64decode(env.payload["data"])
                    h.update(data)
                    f.write(data)
                elif env.type.value == "transfer.end":
                    received_end = env.payload
                    break
                elif env.type.value == "transfer.abort":
                    raise OpDenied("transfer aborted by sender")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    if h.hexdigest() != received_end["sha256"]:
        tmp.unlink(missing_ok=True)
        raise OpDenied("sha256 mismatch — transfer corrupted")

    # collision handling: don't silently overwrite
    final = dest
    n = 1
    while final.exists():
        final = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    os.replace(tmp, final)
    ctx.incoming.pop(transfer_id, None)
    return {"written": str(final), "size": final.stat().st_size, "sha256": h.hexdigest()}


def _update_index_path(ctx: AgentContext, old: Path, new: Path) -> None:
    ctx.conn.execute(
        "UPDATE files SET rel_path = ?, name = ? WHERE name = ? AND deleted = 0",
        (str(new), new.name, old.name),
    )
    ctx.conn.commit()


HANDLERS: dict[str, Callable[[AgentContext, dict], Awaitable[dict]]] = {
    "browse_folder": op_browse_folder,
    "search_files": op_search_files,
    "download_file": op_download_file,
    "rename_file": op_rename_file,
    "move_file": op_move_file,
    "copy_file": op_copy_file,
    "delete_file": op_delete_file,
    "create_folder": op_create_folder,
    "send_file": op_send_file,
}
