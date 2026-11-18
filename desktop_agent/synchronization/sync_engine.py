"""Bidirectional folder sync engine.

Per session:
- watchdog observer on the root -> debounced local ops -> SYNC_EVENT to
  the coordinator (which relays to peer devices)
- incoming SYNC_EVENT -> dedupe via sync_journal -> apply (request content
  over TRANSFER for create/modify; direct ops for delete/rename)
- sync_state rows are the "base" for conflict detection: a file counts as
  conflicting only when BOTH sides changed it since the last sync

Loop prevention: applied op_ids go to sync_journal; locally-caused writes
are also suppressed in the watcher via a short-lived suppress map.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from file_operations.ops import PARTIAL_DIR, OpDenied
from indexing.indexer import DEFAULT_IGNORES, ignored_file_name, sha256_file
from protocol import (
    Envelope,
    MessageType,
    SyncEvent,
    SyncOpType,
    SyncRequest,
    TransferBegin,
    TransferChunk,
    TransferEnd,
)

if TYPE_CHECKING:
    from file_operations.ops import AgentContext

log = logging.getLogger("netsync.sync")

CHUNK = 64 * 1024
DEBOUNCE_SECONDS = 0.4
SUPPRESS_SECONDS = 3.0
SNAPSHOT_DIR_LIMIT = 100_000


class _Watcher(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self._loop = loop
        self._queue = queue

    def on_any_event(self, event: FileSystemEvent) -> None:
        try:
            self._loop.call_soon_threadsafe(
                self._queue.put_nowait,
                (event.event_type, event.src_path,
                 getattr(event, "dest_path", None), event.is_directory),
            )
        except RuntimeError:
            pass  # loop closed during shutdown


@dataclass
class SyncRuntime:
    session_id: str
    root: Path
    peer_device_id: str
    device_id: str
    mode: str
    ctx: "AgentContext"
    paused: bool = False
    observer: Observer | None = None
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    drain_task: asyncio.Task | None = None
    suppress: dict[str, float] = field(default_factory=dict)  # rel_path -> until
    snapshot_replies: int = 0   # reply at most once per session → converge
    applied_ops: int = 0        # peer ops applied locally (progress metric)
    emitted_ops: int = 0        # local ops sent to peer
    file_root: bool = False     # session syncs one file, not a folder


class SyncEngine:
    def __init__(self, ctx: "AgentContext", device_id: str):
        self.ctx = ctx
        self.device_id = device_id
        self.sessions: dict[str, SyncRuntime] = {}

    # ── session lifecycle ────────────────────────────────────────────────

    async def start(self, session_id: str, root: Path, peer: str, mode: str) -> dict:
        if session_id in self.sessions:
            return {"already_running": session_id}
        rt = SyncRuntime(session_id, root, peer, self.device_id, mode, self.ctx)
        rt.file_root = root.is_file()
        self.sessions[session_id] = rt

        rt.observer = Observer()
        watch_dir = root.parent if rt.file_root else root
        rt.observer.schedule(_Watcher(asyncio.get_running_loop(), rt.events),
                             str(watch_dir), recursive=not rt.file_root)
        rt.observer.start()
        rt.drain_task = asyncio.create_task(self._drain(rt))

        # sweep temp dirs older versions littered mid-sync
        if not rt.file_root and root.is_dir():
            for dirpath, _, _ in os.walk(root, topdown=False):
                if os.path.basename(dirpath) == PARTIAL_DIR:
                    try:
                        os.rmdir(dirpath)  # only succeeds when empty
                    except OSError:
                        pass

        await self._send_snapshot(rt)
        log.info("sync %s started on %s (peer %s)", session_id, root, peer)
        return {"session_id": session_id, "root": str(root), "state": "active"}

    async def pause(self, session_id: str) -> dict:
        rt = self.sessions.get(session_id)
        if rt:
            rt.paused = True
        return {"session_id": session_id, "state": "paused"}

    async def resume(self, session_id: str) -> dict:
        rt = self.sessions.get(session_id)
        if rt:
            rt.paused = False
            await self._send_snapshot(rt)  # converge anything missed
        return {"session_id": session_id, "state": "active"}

    async def stop(self, session_id: str) -> dict:
        rt = self.sessions.pop(session_id, None)
        if rt:
            if rt.observer:
                rt.observer.stop()
            if rt.drain_task:
                rt.drain_task.cancel()
        return {"session_id": session_id, "state": "stopped"}

    def stop_all(self) -> None:
        """Called when the WS session drops — agents must not leak watcher
        threads across reconnects."""
        for rt in self.sessions.values():
            if rt.observer:
                rt.observer.stop()
            if rt.drain_task:
                rt.drain_task.cancel()
        self.sessions.clear()

    # ── outbound (local changes) ─────────────────────────────────────────

    async def _drain(self, rt: SyncRuntime) -> None:
        """Debounce watcher events and emit SyncEvents."""
        while True:
            first = await rt.events.get()
            batch = [first]
            # coalesce bursts
            try:
                while True:
                    batch.append(
                        await asyncio.wait_for(rt.events.get(), DEBOUNCE_SECONDS)
                    )
            except asyncio.TimeoutError:
                pass
            try:
                await self._emit_batch(rt, batch)
            except Exception:
                log.exception("sync emit failed")

    async def _emit_batch(self, rt: SyncRuntime, batch: list) -> None:
        if rt.paused:
            return
        seen: dict[str, tuple] = {}  # rel_path -> (op, path, dest, priority)

        def put(rel: str, op: str, p: Path, old=None, pri: int = 2) -> None:
            cur = seen.get(rel)
            if cur is None or pri >= cur[3]:
                seen[rel] = (op, p, old, pri)

        for ev_type, src, dest, is_dir in batch:
            rel = self._rel(rt, Path(dest or src))
            if rel is None or self._ignored(rel) or self._suppressed(rt, rel):
                continue
            p = Path(dest or src)
            if ev_type == "moved" and dest:
                old_rel = self._rel(rt, Path(src))
                if old_rel and not self._ignored(old_rel):
                    # a true rename: the peer moves it in place — zero bytes
                    put(rel, "rename", p, old_rel, 3)
                else:
                    put(rel, "dir" if p.is_dir() else "modify", p)
                if p.is_dir():
                    # still emit the subtree so a peer that never had the
                    # folder converges instead of getting an empty one
                    for dp, dns, fns in os.walk(p):
                        dns[:] = [d for d in dns if d not in DEFAULT_IGNORES]
                        for dd in dns:
                            r2 = self._rel(rt, Path(dp) / dd)
                            if r2:
                                put(r2, "dir", Path(dp) / dd, None, 1)
                        for fn in fns:
                            if fn in DEFAULT_IGNORES or ignored_file_name(fn):
                                continue
                            fp = Path(dp) / fn
                            r2 = self._rel(rt, fp)
                            if r2:
                                put(r2, "modify", fp, None, 1)
            elif p.is_dir():
                put(rel, "dir", p)
            elif ev_type == "deleted":
                put(rel, "rmdir" if is_dir else "delete", p, None, 4)
            else:
                put(rel, "modify", p)

        for rel, (op, path, dest, _pri) in seen.items():
            if rt.paused:
                break
            ev = self._build_event(rt, rel, op, path, dest)
            if ev:
                await self._send_event(rt, ev)
                self._record_state(rt, rel, ev.sha256 or "", ev.mtime)

    def _build_event(self, rt, rel, op, path, dest):
        op_id = str(uuid.uuid4())
        if op == "delete":
            return SyncEvent(session_id=rt.session_id, op_id=op_id,
                             op=SyncOpType.DELETE, rel_path=rel,
                             sha256=self._base_sha(rt, rel),
                             from_device=self.device_id)
        if op == "dir":
            return SyncEvent(session_id=rt.session_id, op_id=op_id,
                             op=SyncOpType.DIR, rel_path=rel,
                             from_device=self.device_id)
        if op == "rename":
            # `dest` carries the old rel_path for rename ops
            if path.is_dir():
                return SyncEvent(session_id=rt.session_id, op_id=op_id,
                                 op=SyncOpType.RENAME, rel_path=rel,
                                 old_rel_path=dest, from_device=self.device_id)
            st = path.stat()
            return SyncEvent(session_id=rt.session_id, op_id=op_id,
                             op=SyncOpType.RENAME, rel_path=rel,
                             old_rel_path=dest, sha256=sha256_file(path),
                             size=st.st_size, mtime=st.st_mtime,
                             from_device=self.device_id)
        if op == "rmdir":
            return SyncEvent(session_id=rt.session_id, op_id=op_id,
                             op=SyncOpType.RMDIR, rel_path=rel,
                             from_device=self.device_id)
        try:
            st = path.stat()
        except OSError:
            return None
        if not path.is_file():
            return None
        return SyncEvent(session_id=rt.session_id, op_id=op_id,
                         op=SyncOpType.MODIFY, rel_path=rel,
                         sha256=sha256_file(path), size=st.st_size,
                         mtime=st.st_mtime, from_device=self.device_id)

    async def _send_snapshot(self, rt: SyncRuntime) -> None:
        entries = []
        dirs: list[str] = []
        if rt.file_root and rt.root.is_file():
            st = rt.root.stat()
            entries.append({"rel_path": rt.root.name, "sha256": sha256_file(rt.root),
                            "size": st.st_size, "mtime": st.st_mtime})
        for dirpath, dirnames, filenames in os.walk(rt.root):
            if rt.file_root:
                break
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORES]
            for d in dirnames:
                rel = self._rel(rt, Path(dirpath) / d)
                if rel is not None:
                    dirs.append(rel)
            for fname in filenames:
                if fname in DEFAULT_IGNORES or ignored_file_name(fname):
                    continue
                full = Path(dirpath) / fname
                rel = self._rel(rt, full)
                if rel is None:
                    continue
                try:
                    st = full.stat()
                    entries.append({"rel_path": rel, "sha256": sha256_file(full),
                                    "size": st.st_size, "mtime": st.st_mtime})
                except OSError:
                    continue
                if len(entries) >= SNAPSHOT_DIR_LIMIT:
                    break
        ev = SyncEvent(session_id=rt.session_id, op_id=str(uuid.uuid4()),
                       op=SyncOpType.SNAPSHOT, rel_path="", entries=entries,
                       dirs=dirs, from_device=self.device_id)
        await self._send_event(rt, ev)

    async def _send_event(self, rt: SyncRuntime, ev: SyncEvent) -> None:
        rt.emitted_ops += 1
        self._journal(rt, ev.op_id, ev.op.value, ev.rel_path)
        await self.ctx.send(
            Envelope(type=MessageType.SYNC_EVENT, payload=ev.model_dump()).model_dump_json()
        )

    # ── inbound (peer changes) ───────────────────────────────────────────

    async def on_sync_event(self, env: Envelope) -> None:
        try:
            ev = SyncEvent.model_validate(env.payload)
        except Exception:
            log.warning("unreadable sync event dropped")
            return
        rt = self.sessions.get(ev.session_id)
        if rt is None:
            return
        if self._journaled(rt, ev.op_id):
            return  # our own op echoed back, or already applied
        self._journal(rt, ev.op_id, ev.op.value, ev.rel_path)
        rt.applied_ops += 1

        if ev.op is SyncOpType.SNAPSHOT:
            # our startup snapshot may have raced past the peer's start —
            # reply once so both sides always receive each other's listing
            if rt.snapshot_replies == 0:
                rt.snapshot_replies = 1
                await self._send_snapshot(rt)
            await self._apply_snapshot(rt, ev)
        elif ev.op is SyncOpType.DIR:
            await self._apply_dir(rt, ev)
        elif ev.op is SyncOpType.RMDIR:
            await self._apply_rmdir(rt, ev)
        elif ev.op is SyncOpType.DELETE:
            await self._apply_delete(rt, ev)
        elif ev.op is SyncOpType.RENAME:
            await self._apply_rename(rt, ev)
        else:  # CREATE / MODIFY
            await self._apply_write(rt, ev)

    async def on_sync_request(self, env: Envelope) -> None:
        """Peer wants file content for an op we emitted."""
        req = SyncRequest.model_validate(env.payload)
        rt = self.sessions.get(req.session_id)
        if rt is None:
            return
        path = (rt.root / req.rel_path).resolve()
        try:
            path.relative_to(rt.root.resolve())
        except ValueError:
            return
        if not path.is_file():
            return
        await self._push_file(rt, path, req.transfer_id, req.to_device,
                              rel_path=req.rel_path)

    async def _push_file(self, rt, path: Path, transfer_id: str, dest: str,
                         rel_path: str = "") -> None:
        digest = sha256_file(path)
        size = path.stat().st_size
        state = self.ctx.transfer_state(transfer_id)
        state.direction = "out"
        state.name = path.name
        state.size = size
        state.dest = path
        state.rel_path = rel_path
        state.meta = {"session_id": rt.session_id}
        await self.ctx.send(Envelope(
            type=MessageType.TRANSFER_BEGIN,
            payload=TransferBegin(
                transfer_id=transfer_id, direction="push", name=path.name,
                size=size, sha256=digest,
                meta={"dest_device": dest, "session_id": rt.session_id},
            ).model_dump(),
        ).model_dump_json())
        seq = 0
        try:
            with path.open("rb") as f:
                while chunk := f.read(CHUNK):
                    await self.ctx.send(Envelope(
                        type=MessageType.TRANSFER_CHUNK,
                        payload=TransferChunk(
                            transfer_id=transfer_id, seq=seq,
                            data=base64.b64encode(chunk).decode(),
                        ).model_dump(),
                    ).model_dump_json())
                    state.received += len(chunk)
                    seq += 1
            await self.ctx.send(Envelope(
                type=MessageType.TRANSFER_END,
                payload=TransferEnd(transfer_id=transfer_id, seq=seq, sha256=digest).model_dump(),
            ).model_dump_json())
        except Exception:
            self.ctx.note_transfer(state, ok=False)
            raise
        self.ctx.note_transfer(state, ok=True)

    async def _apply_dir(self, rt: SyncRuntime, ev: SyncEvent) -> None:
        """Peer created a folder — make it here (empty folders sync too)."""
        rel = ev.rel_path
        if self._ignored(rel):
            return
        target = (rt.root / rel).resolve()
        try:
            target.relative_to(rt.root.resolve())
        except ValueError:
            return
        self._mark_suppressed(rt, rel)
        target.mkdir(parents=True, exist_ok=True)

    async def _apply_rmdir(self, rt: SyncRuntime, ev: SyncEvent) -> None:
        """Peer removed or renamed a folder — drop it only if EMPTY, so
        rename ghosts disappear without ever deleting real content."""
        rel = ev.rel_path
        if self._ignored(rel):
            return
        target = (rt.root / rel).resolve()
        try:
            target.relative_to(rt.root.resolve())
        except ValueError:
            return
        self._mark_suppressed(rt, rel)
        try:
            target.rmdir()  # OSError if missing or non-empty — both fine
        except OSError:
            pass

    async def _apply_snapshot(self, rt: SyncRuntime, ev: SyncEvent) -> None:
        """Request whatever we're missing or differ on."""
        for rel in ev.dirs:
            if self._ignored(rel):
                continue
            target = (rt.root / rel).resolve()
            try:
                target.relative_to(rt.root.resolve())
            except ValueError:
                continue
            self._mark_suppressed(rt, rel)
            target.mkdir(parents=True, exist_ok=True)
        for entry in ev.entries:
            rel = entry["rel_path"]
            local = rt.root / rel
            local_sha = sha256_file(local) if local.is_file() else None
            if local_sha == entry["sha256"]:
                continue
            pseudo = SyncEvent(
                session_id=ev.session_id, op_id=str(uuid.uuid4()),
                op=SyncOpType.MODIFY, rel_path=rel, sha256=entry["sha256"],
                size=entry["size"], mtime=entry["mtime"],
                from_device=ev.from_device,
            )
            await self._apply_write(rt, pseudo, base_sha=entry["sha256"] if local_sha else None)

    async def _apply_delete(self, rt: SyncRuntime, ev: SyncEvent) -> None:
        """Peer deleted a file — remove our copy only when it still matches
        a known version. A locally edited copy always survives a delete."""
        rel = ev.rel_path
        if self._ignored(rel):
            return
        target = (rt.root / rel).resolve()
        try:
            target.relative_to(rt.root.resolve())
        except ValueError:
            return
        self._mark_suppressed(rt, rel)
        if target.is_file():
            known = {s for s in (self._base_sha(rt, rel), ev.sha256) if s}
            if sha256_file(target) in known:
                try:
                    target.unlink()
                except OSError:
                    pass
                # drop parent dirs left empty by the delete
                parent = target.parent
                while parent != rt.root and parent.exists():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    self._mark_suppressed(rt, self._rel(rt, parent) or rel)
                    parent = parent.parent
        self._clear_state(rt, rel)

    async def _apply_rename(self, rt: SyncRuntime, ev: SyncEvent) -> None:
        """A real rename/move — performed with os.rename so no bytes cross
        the wire. Falls back to fetching when we never had the item."""
        rel, old = ev.rel_path, ev.old_rel_path
        if not old or self._ignored(rel) or self._ignored(old):
            return
        root = rt.root.resolve()
        src = (rt.root / old).resolve()
        dst = (rt.root / rel).resolve()
        try:
            src.relative_to(root)
            dst.relative_to(root)
        except ValueError:
            log.warning("sync path escape blocked: %s -> %s", old, rel)
            return
        if not src.exists():
            if ev.sha256:
                await self._apply_write(rt, ev)   # never had it — fetch it
            else:
                await self._apply_dir(rt, ev)     # never had the dir — make it
            return
        self._mark_suppressed(rt, old)
        self._mark_suppressed(rt, rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst = dst.with_name(
                f"{dst.stem}.conflict-{ev.from_device[:8]}{dst.suffix}")
            self._mark_suppressed(rt, self._rel(rt, dst) or rel)
            log.warning("rename conflict on %s — wrote %s", rel, dst.name)
        src.rename(dst)
        if dst.is_dir():
            for dp, dns, fns in os.walk(dst):
                dns[:] = [d for d in dns if d not in DEFAULT_IGNORES]
                for n in (*dns, *fns):
                    r2 = self._rel(rt, Path(dp) / n)
                    if r2:
                        self._mark_suppressed(rt, r2)
        # slide the base-state rows over to the new name
        for r in self.ctx.conn.execute(
                "SELECT rel_path FROM sync_state WHERE session_id=?",
                (rt.session_id,)).fetchall():
            rp = r["rel_path"]
            if rp == old or rp.startswith(old + os.sep):
                self.ctx.conn.execute(
                    "UPDATE sync_state SET rel_path=? "
                    "WHERE session_id=? AND rel_path=?",
                    (rel + rp[len(old):], rt.session_id, rp))
        self.ctx.conn.commit()

    async def _apply_write(self, rt: SyncRuntime, ev: SyncEvent, base_sha: str | None = None) -> None:
        rel = ev.rel_path
        if self._ignored(rel):
            return
        target = (rt.root / rel).resolve()
        try:
            target.relative_to(rt.root.resolve())
        except ValueError:
            log.warning("sync path escape blocked: %s", rel)
            return

        local_sha = sha256_file(target) if target.is_file() else None
        if local_sha == ev.sha256:
            self._record_state(rt, rel, ev.sha256 or "", ev.mtime)
            return

        base = base_sha if base_sha is not None else self._base_sha(rt, rel)
        conflict = bool(local_sha and base and local_sha != base)

        # a copy of a file we already have lands as a local clone — the
        # content never crosses the wire a second time
        clone = self._find_by_sha(rt, ev.sha256) if ev.sha256 else None
        if clone is None:
            content = await self._fetch(rt, ev, target)
            if content is None:
                return

        dest = target
        if conflict:
            dest = target.with_name(
                f"{target.stem}.conflict-{ev.from_device[:8]}{target.suffix}"
            )
            log.warning("conflict on %s — wrote %s", rel, dest.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._mark_suppressed(rt, self._rel(rt, dest) or rel)
        tmp = dest.parent / PARTIAL_DIR / f"{uuid.uuid4().hex}.part"
        tmp.parent.mkdir(exist_ok=True)
        if clone is not None:
            shutil.copyfile(clone, tmp)
        else:
            tmp.write_bytes(content)
        os.replace(tmp, dest)
        try:
            tmp.parent.rmdir()  # temp dir served its turn — don't litter
        except OSError:
            pass
        if not conflict:
            self._record_state(rt, rel, ev.sha256 or "", ev.mtime)

    async def _fetch(
        self, rt: SyncRuntime, ev: SyncEvent, dest_hint: Path | None = None
    ) -> bytes | None:
        transfer_id = str(uuid.uuid4())
        state = self.ctx.transfer_state(transfer_id)
        state.name = Path(ev.rel_path).name
        state.rel_path = ev.rel_path
        state.size = ev.size or 0
        state.direction = "in"
        if dest_hint is not None:
            state.dest = dest_hint
        await self.ctx.send(Envelope(
            type=MessageType.SYNC_REQUEST,
            payload=SyncRequest(
                session_id=rt.session_id, op_id=ev.op_id, rel_path=ev.rel_path,
                transfer_id=transfer_id, origin_device=ev.from_device,
                to_device=self.device_id,
            ).model_dump(),
        ).model_dump_json())
        buf = bytearray()
        try:
            while True:
                env = await asyncio.wait_for(state.queue.get(), timeout=60)
                if env.type is MessageType.TRANSFER_CHUNK:
                    buf.extend(base64.b64decode(env.payload["data"]))
                elif env.type is MessageType.TRANSFER_END:
                    break
                elif env.type is MessageType.TRANSFER_ABORT:
                    self.ctx.note_transfer(state, ok=False)
                    return None
        except asyncio.TimeoutError:
            self.ctx.note_transfer(state, ok=False)
            return None
        if hashlib.sha256(bytes(buf)).hexdigest() != env.payload["sha256"]:
            self.ctx.note_transfer(state, ok=False)
            log.warning("sync transfer hash mismatch on %s", ev.rel_path)
            return None
        self.ctx.note_transfer(state, ok=True)
        return bytes(buf)

    # ── helpers ──────────────────────────────────────────────────────────

    def _rel(self, rt: SyncRuntime, path: Path) -> str | None:
        if rt.file_root:
            # only events for the synced file itself count
            return rt.root.name if path.resolve() == rt.root.resolve() else None
        try:
            return str(path.resolve().relative_to(rt.root.resolve()))
        except ValueError:
            return None

    def _ignored(self, rel: str) -> bool:
        parts = Path(rel).parts
        return any(p in DEFAULT_IGNORES for p in parts) or (
            parts and ignored_file_name(parts[-1]))

    def _suppressed(self, rt: SyncRuntime, rel: str) -> bool:
        until = rt.suppress.get(rel, 0)
        if time.monotonic() < until:
            return True
        rt.suppress.pop(rel, None)
        return False

    def _mark_suppressed(self, rt: SyncRuntime, rel: str) -> None:
        rt.suppress[rel] = time.monotonic() + SUPPRESS_SECONDS

    def _journaled(self, rt: SyncRuntime, op_id: str) -> bool:
        return self.ctx.conn.execute(
            "SELECT 1 FROM sync_journal WHERE op_id = ?", (op_id,)
        ).fetchone() is not None

    def _journal(self, rt: SyncRuntime, op_id: str, op_type: str, rel: str) -> None:
        self.ctx.conn.execute(
            "INSERT OR IGNORE INTO sync_journal (op_id, session_id, op_type, rel_path) "
            "VALUES (?,?,?,?)",
            (op_id, rt.session_id, op_type, rel),
        )
        self.ctx.conn.commit()

    def _base_sha(self, rt: SyncRuntime, rel: str) -> str | None:
        row = self.ctx.conn.execute(
            "SELECT sha256 FROM sync_state WHERE session_id=? AND rel_path=?",
            (rt.session_id, rel),
        ).fetchone()
        return row["sha256"] if row else None

    def _find_by_sha(self, rt: SyncRuntime, sha: str) -> Path | None:
        """An existing file inside this sync root with identical content —
        lets a peer's 'copy' land as a local clone instead of a transfer."""
        root = rt.root.resolve()
        rels = [r["rel_path"] for r in self.ctx.conn.execute(
            "SELECT rel_path FROM sync_state WHERE session_id=? AND sha256=?",
            (rt.session_id, sha)).fetchall()]
        folder = self.ctx.conn.execute(
            "SELECT id FROM indexed_folders WHERE path=?",
            (str(root),)).fetchone()
        if folder is not None:
            rels += [r["rel_path"] for r in self.ctx.conn.execute(
                "SELECT rel_path FROM files WHERE folder_id=? AND sha256=? "
                "AND deleted=0", (folder["id"], sha)).fetchall()]
        for rel in rels:
            cand = (rt.root / rel).resolve()
            try:
                cand.relative_to(root)
            except ValueError:
                continue
            if cand.is_file() and sha256_file(cand) == sha:
                return cand
        return None

    def _record_state(self, rt: SyncRuntime, rel: str, sha: str, mtime: float) -> None:
        if not sha:
            return
        self.ctx.conn.execute(
            "INSERT INTO sync_state (session_id, rel_path, sha256, mtime) VALUES (?,?,?,?) "
            "ON CONFLICT(session_id, rel_path) DO UPDATE SET "
            "sha256=excluded.sha256, mtime=excluded.mtime, updated_at=datetime('now')",
            (rt.session_id, rel, sha, mtime),
        )
        self.ctx.conn.commit()

    def _clear_state(self, rt: SyncRuntime, rel: str) -> None:
        self.ctx.conn.execute(
            "DELETE FROM sync_state WHERE session_id=? AND rel_path=?",
            (rt.session_id, rel),
        )
        self.ctx.conn.commit()


# ── tool handlers (registered into ops.HANDLERS) ─────────────────────────────

async def op_start_sync(ctx: "AgentContext", args: dict) -> dict:
    root = ctx.check_path(args["root"], write=True)
    if not root.is_dir() and not root.is_file():
        raise OpDenied("sync root must be a folder or file")
    return await ctx.sync.start(
        args["session_id"], root, args["peer_device_id"], args.get("mode", "live")
    )


async def op_pause_sync(ctx: "AgentContext", args: dict) -> dict:
    return await ctx.sync.pause(args["session_id"])


async def op_resume_sync(ctx: "AgentContext", args: dict) -> dict:
    return await ctx.sync.resume(args["session_id"])


async def op_stop_sync(ctx: "AgentContext", args: dict) -> dict:
    return await ctx.sync.stop(args["session_id"])


async def op_get_device_status(ctx: "AgentContext", args: dict) -> dict:
    return {
        "transfers": [
            {
                "id": s.transfer_id, "name": s.name, "size": s.size,
                "received": s.received, "direction": s.direction,
                "rel_path": s.rel_path,
                "dest": str(s.dest) if s.dest else "",
                "session_id": (s.meta or {}).get("session_id", ""),
                "done": False, "ok": True,
            }
            for s in ctx.incoming.values()
        ] + ctx.recent_transfers[-10:],
        "sync_sessions": {
            sid: {
                "root": str(rt.root), "paused": rt.paused, "mode": rt.mode,
                "applied_ops": rt.applied_ops, "emitted_ops": rt.emitted_ops,
                "pending_ops": rt.events.qsize(),
            }
            for sid, rt in ctx.sync.sessions.items()
        }
    }


SYNC_HANDLERS = {
    "start_sync": op_start_sync,
    "pause_sync": op_pause_sync,
    "resume_sync": op_resume_sync,
    "stop_sync": op_stop_sync,
    "get_device_status": op_get_device_status,
}
