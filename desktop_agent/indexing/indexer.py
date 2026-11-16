"""Local folder indexing into SQLite FTS5.

Only folders the local user explicitly registers are indexed — indexing is
never implicit. Reindexing reconciles on-disk state (adds, modifies, marks
missing files deleted) and preserves stable file_ids across renames.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

# Software-project defaults per spec; user-configurable via agent_settings.
DEFAULT_IGNORES: frozenset[str] = frozenset({
    "node_modules", ".next", ".git", ".vercel", "__pycache__",
    ".env", ".env.local", ".env.development", ".env.production",
    "dist", "build", ".turbo", ".cache", ".netsync-partial",
})

CHUNK = 1024 * 1024
HASH_MAX_SIZE = 200 * 1024 * 1024  # skip hashing files >200MB at index time


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class IndexStats:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0


def register_folder(
    conn: sqlite3.Connection,
    path: str | Path,
    label: str = "",
    access: str = "read",
) -> int:
    if access not in ("none", "read", "readwrite"):
        raise ValueError(f"bad access level: {access}")
    p = str(Path(path).resolve())
    conn.execute(
        "INSERT INTO indexed_folders (path, label, access) VALUES (?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET label = excluded.label, access = excluded.access",
        (p, label, access),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM indexed_folders WHERE path = ?", (p,)
    ).fetchone()["id"]


def index_folder(
    conn: sqlite3.Connection,
    folder_id: int,
    ignores: frozenset[str] = DEFAULT_IGNORES,
) -> IndexStats:
    """Walk a registered folder and reconcile the `files` table."""
    row = conn.execute(
        "SELECT path FROM indexed_folders WHERE id = ?", (folder_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"unknown folder_id {folder_id}")
    root = Path(row["path"])
    stats = IndexStats()
    seen: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignores]
        for fname in filenames:
            if fname in ignores:
                stats.skipped += 1
                continue
            full = Path(dirpath) / fname
            try:
                rel = str(full.relative_to(root))
                st = full.stat()
            except (OSError, ValueError):
                stats.skipped += 1
                continue
            seen.add(rel)

            existing = conn.execute(
                "SELECT id, size, mtime FROM files "
                "WHERE folder_id = ? AND rel_path = ? AND deleted = 0",
                (folder_id, rel),
            ).fetchone()

            digest = None
            if st.st_size <= HASH_MAX_SIZE:
                try:
                    digest = sha256_file(full)
                except OSError:
                    pass

            if existing and existing["size"] == st.st_size and existing["mtime"] == st.st_mtime:
                continue  # unchanged

            if existing:
                conn.execute(
                    "UPDATE files SET name=?, ext=?, size=?, mtime=?, sha256=?, deleted=0 "
                    "WHERE id=?",
                    (fname, full.suffix.lower(), st.st_size, st.st_mtime, digest, existing["id"]),
                )
                _record_revision(conn, existing["id"], digest, st.st_size, st.st_mtime)
                stats.updated += 1
            else:
                conn.execute(
                    "INSERT INTO files (folder_id, file_id, rel_path, name, ext, size, mtime, sha256) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (folder_id, str(uuid.uuid4()), rel, fname, full.suffix.lower(),
                     st.st_size, st.st_mtime, digest),
                )
                new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                _record_revision(conn, new_id, digest, st.st_size, st.st_mtime)
                stats.added += 1

    # anything indexed but not seen on disk is gone
    stale = conn.execute(
        "SELECT id FROM files WHERE folder_id = ? AND deleted = 0", (folder_id,)
    ).fetchall()
    for s in stale:
        rel = conn.execute("SELECT rel_path FROM files WHERE id = ?", (s["id"],)).fetchone()["rel_path"]
        if rel not in seen:
            conn.execute("UPDATE files SET deleted = 1 WHERE id = ?", (s["id"],))
            stats.deleted += 1

    conn.commit()
    return stats


def _record_revision(conn, file_row_id: int, digest: str | None, size: int, mtime: float) -> None:
    conn.execute(
        "INSERT INTO file_revisions (file_row_id, sha256, size, mtime) VALUES (?,?,?,?)",
        (file_row_id, digest or "", size, mtime),
    )


def _fts_query(user_query: str) -> str:
    """Turn free text into a safe FTS5 query: quoted tokens, prefix match."""
    tokens = [t for t in user_query.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    return " ".join(f'"{t}"*' for t in tokens)


def search_files(
    conn: sqlite3.Connection,
    query: str,
    ext: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """FTS5 prefix search over name/rel_path/ext. Returns metadata only.

    `rel_path` is relative to its indexed folder; `path` is absolute and is
    what remote operations (download/rename/…) must be given."""
    if query.strip():
        sql = """
            SELECT f.file_id, f.rel_path, f.name, f.ext, f.size, f.mtime,
                   f.sha256, f.folder_id, d.path AS root
            FROM files_fts
            JOIN files f ON f.id = files_fts.rowid
            JOIN indexed_folders d ON d.id = f.folder_id
            WHERE files_fts MATCH ? AND f.deleted = 0 AND d.access != 'none'
        """
        params: list = [_fts_query(query)]
    else:
        sql = """
            SELECT f.file_id, f.rel_path, f.name, f.ext, f.size, f.mtime,
                   f.sha256, f.folder_id, d.path AS root
            FROM files f JOIN indexed_folders d ON d.id = f.folder_id
            WHERE f.deleted = 0 AND d.access != 'none'
        """
        params = []
    if ext:
        sql += " AND f.ext = ?"
        params.append(ext if ext.startswith(".") else f".{ext}")
    sql += " ORDER BY f.name LIMIT ? OFFSET ?"
    params += [limit, offset]
    out = []
    for r in conn.execute(sql, params).fetchall():
        row = dict(r)
        row["path"] = str(Path(row.pop("root")) / row["rel_path"])
        out.append(row)
    return out


def list_folder_children(conn: sqlite3.Connection, folder_id: int, prefix: str = "") -> list[dict]:
    """Direct children of a path prefix inside an indexed folder."""
    like = f"{prefix}%" if prefix else "%"
    rows = conn.execute(
        "SELECT rel_path, name, ext, size, mtime, file_id FROM files "
        "WHERE folder_id = ? AND deleted = 0 AND rel_path LIKE ?",
        (folder_id, like),
    ).fetchall()
    depth = prefix.count(os.sep) + (1 if prefix else 0)
    out, dirs = [], set()
    for r in rows:
        parts = r["rel_path"].split(os.sep)
        if len(parts) == depth + 1:
            out.append(dict(r))
        else:
            dirs.add(os.sep.join(parts[: depth + 1]))
    for d in sorted(dirs):
        out.append({"rel_path": d, "name": Path(d).name, "is_dir": True})
    return out
