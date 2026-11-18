"""Folder management — lets the device OWNER choose shared folders from the
web dashboard instead of the CLI.

The coordinator only dispatches these tools for the device's owner. The
agent adds its own hard limit: system and credential locations can never
be shared, regardless of who asks (see is_blocked).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import string
from pathlib import Path

from file_operations.ops import AgentContext, OpDenied
from indexing.indexer import index_folder, register_folder

log = logging.getLogger("netsync.folders")

ACCESS_LEVELS = ("read", "readwrite")

# Credential / config folders under the user profile that must never be shared.
_PROFILE_SECRETS = (
    "AppData", ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker",
    ".config", ".npmrc", ".git-credentials",
)


def _norm(p: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def blocked_paths(data_dir: Path | None = None) -> list[Path]:
    env = os.environ
    out: list[Path] = []
    for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                "APPDATA", "LOCALAPPDATA"):
        if env.get(var):
            out.append(Path(env[var]))
    home = Path.home()
    out += [home / name for name in _PROFILE_SECRETS]
    if data_dir is not None:
        out.append(data_dir)
    return out


def is_blocked(path: Path, data_dir: Path | None = None) -> str | None:
    """Reason string if `path` may not be shared, else None.

    Blocked if it IS, is INSIDE, or CONTAINS a sensitive location; drive
    roots and the bare home folder therefore always fail (they contain
    AppData / .ssh)."""
    target = _norm(path.resolve())
    if Path(target).parent == Path(target):
        return "whole drives cannot be shared"
    if target == _norm(Path.home()):
        return "your entire user folder cannot be shared — pick a subfolder"
    for b in blocked_paths(data_dir):
        nb = _norm(b)
        if target == nb or target.startswith(nb + os.sep):
            return f"system or credential folder ({b}) cannot be shared"
        if nb.startswith(target + os.sep):
            return f"folder contains a protected location ({b})"
    return None


def _quick_locations() -> list[dict]:
    home = Path.home()
    out = []
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
        p = home / name
        if p.is_dir():
            out.append({"name": name, "path": str(p), "kind": "quick"})
    return out


def _drives() -> list[dict]:
    if os.name != "nt":
        return [{"name": "/", "path": "/", "kind": "drive"}]
    return [
        {"name": f"{d}:", "path": f"{d}:\\", "kind": "drive"}
        for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")
    ]


async def op_list_local_dirs(ctx: AgentContext, args: dict) -> dict:
    """Directory-only listing for the dashboard folder picker. Never
    returns file names or contents."""
    raw = args.get("path", "")
    if not raw:
        return {"path": "", "parent": None,
                "entries": _quick_locations() + _drives()}
    target = Path(raw)
    if not target.is_absolute() or not target.is_dir():
        raise OpDenied("not a directory")
    target = target.resolve()
    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise OpDenied(f"cannot open folder: {exc.strerror or exc}")
    include_files = bool(args.get("files"))
    for child in children:
        try:
            is_dir = child.is_dir()
            if (not is_dir and not include_files) or child.name.startswith(("$", ".")):
                continue
        except OSError:
            continue
        reason = is_blocked(child, ctx.data_dir)
        entries.append({"name": child.name, "path": str(child),
                        "kind": "dir" if is_dir else "file", "blocked": reason})
    parent = None if target.parent == target else str(target.parent)
    return {"path": str(target), "parent": parent,
            "blocked": is_blocked(target, ctx.data_dir), "entries": entries}


def _folder_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT f.id, f.path, f.label, f.access, f.created_at, f.last_indexed_at,
               COUNT(x.id) AS file_count, COALESCE(SUM(x.size), 0) AS total_size
        FROM indexed_folders f
        LEFT JOIN files x ON x.folder_id = f.id AND x.deleted = 0
        GROUP BY f.id ORDER BY f.label, f.path
    """).fetchall()
    return [dict(r) for r in rows]


def _prune_missing(conn: sqlite3.Connection) -> None:
    """Drop records for folders deleted on disk. A record whose whole drive
    is offline (USB stick, network share) is kept — it may come back."""
    rows = conn.execute("SELECT id, path FROM indexed_folders").fetchall()
    gone = []
    for r in rows:
        p = Path(r["path"])
        if not p.exists() and Path(p.anchor).exists():
            gone.append(r["id"])
    if not gone:
        return
    conn.executemany(
        "DELETE FROM indexed_folders WHERE id = ?", [(i,) for i in gone])
    conn.commit()


async def op_list_folders(ctx: AgentContext, args: dict) -> dict:
    _prune_missing(ctx.conn)
    folders = _folder_rows(ctx.conn)
    for f in folders:
        f["indexing"] = f["id"] in ctx.indexing
    return {"folders": folders}


def _index_in_thread(data_dir: Path, folder_id: int) -> dict:
    # sqlite connections are per-thread: open a dedicated one
    from database.db import connect
    conn = connect(data_dir)
    try:
        stats = index_folder(conn, folder_id)
        conn.execute(
            "UPDATE indexed_folders SET last_indexed_at = datetime('now') WHERE id = ?",
            (folder_id,),
        )
        conn.commit()
        return stats.__dict__
    finally:
        conn.close()


async def _run_index(ctx: AgentContext, folder_id: int) -> dict | None:
    """Caller must already have added folder_id to ctx.indexing."""
    try:
        return await asyncio.to_thread(_index_in_thread, ctx.data_dir, folder_id)
    except Exception:
        log.exception("indexing folder %s failed", folder_id)
        return None
    finally:
        ctx.indexing.discard(folder_id)


async def reindex(ctx: AgentContext, folder_id: int) -> dict | None:
    if folder_id in ctx.indexing:
        return None
    ctx.indexing.add(folder_id)
    return await _run_index(ctx, folder_id)


def _find(ctx: AgentContext, raw: str) -> dict:
    target = _norm(Path(raw).resolve())
    for f in _folder_rows(ctx.conn):
        if _norm(f["path"]) == target:
            return f
    raise OpDenied("folder is not shared on this device")


def _unique_name(target: Path, conn: sqlite3.Connection) -> Path:
    """First free candidate: `name`, `name (2)`, `name (3)`… Free means
    neither on disk nor already a registered share — two incoming syncs
    must never silently merge into one local folder."""
    taken = {_norm(f["path"]) for f in _folder_rows(conn)}
    for i in range(100):
        cand = target if i == 0 else target.with_name(f"{target.name} ({i + 1})")
        if not cand.exists() and _norm(cand) not in taken:
            return cand
    raise OpDenied("couldn't find a free folder name for the sync")


async def op_add_folder(ctx: AgentContext, args: dict) -> dict:
    raw = args.get("path", "")
    access = args.get("access", "read")
    if access not in ACCESS_LEVELS:
        raise OpDenied("access must be 'read' or 'readwrite'")
    target = Path(raw)
    if not raw or not target.is_absolute():
        raise OpDenied("not a file or folder on this computer")
    target = target.resolve()
    unique = bool(args.get("unique"))
    if unique:
        target = _unique_name(target, ctx.conn)
    exists = target.is_dir() or target.is_file()
    if not exists and not (args.get("create") or unique):
        raise OpDenied("not a file or folder on this computer")
    if reason := is_blocked(target, ctx.data_dir):
        raise OpDenied(reason)
    if not exists:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OpDenied(f"couldn't create folder: {exc.strerror or exc}")
    label = (target.name if unique else
             (args.get("label") or target.name or str(target)))[:120]
    folder_id = register_folder(ctx.conn, target, label=label, access=access)
    ctx.indexing.add(folder_id)  # visible as "indexing" immediately
    task = asyncio.create_task(_run_index(ctx, folder_id))
    ctx.background.add(task)
    task.add_done_callback(ctx.background.discard)
    log.info("folder shared from dashboard: %s (%s)", target, access)
    return {"id": folder_id, "path": str(target), "label": label,
            "access": access, "indexing": True}


async def op_remove_folder(ctx: AgentContext, args: dict) -> dict:
    f = _find(ctx, args.get("path", ""))
    ctx.conn.execute("DELETE FROM indexed_folders WHERE id = ?", (f["id"],))
    ctx.conn.commit()
    log.info("folder unshared: %s", f["path"])
    return {"removed": f["path"]}


async def op_set_folder_access(ctx: AgentContext, args: dict) -> dict:
    access = args.get("access")
    if access not in ACCESS_LEVELS:
        raise OpDenied("access must be 'read' or 'readwrite'")
    f = _find(ctx, args.get("path", ""))
    ctx.conn.execute(
        "UPDATE indexed_folders SET access = ? WHERE id = ?", (access, f["id"])
    )
    ctx.conn.commit()
    return {"path": f["path"], "access": access}


async def op_reindex_folder(ctx: AgentContext, args: dict) -> dict:
    f = _find(ctx, args.get("path", ""))
    stats = await reindex(ctx, f["id"])
    return {"path": f["path"], "stats": stats, "already_running": stats is None}


async def periodic_reindex(ctx: AgentContext, interval: float = 600) -> None:
    """Keep search results fresh for folders not under live sync."""
    while True:
        await asyncio.sleep(interval)
        for f in _folder_rows(ctx.conn):
            await reindex(ctx, f["id"])


FOLDER_HANDLERS = {
    "list_local_dirs": op_list_local_dirs,
    "list_folders": op_list_folders,
    "add_folder": op_add_folder,
    "remove_folder": op_remove_folder,
    "set_folder_access": op_set_folder_access,
    "reindex_folder": op_reindex_folder,
}
