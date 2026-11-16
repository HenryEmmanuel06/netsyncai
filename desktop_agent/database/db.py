"""SQLite connection + schema bootstrap for the desktop agent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def default_data_dir() -> Path:
    """Writable per-user data dir — never next to the executable."""
    import os

    override = os.environ.get("NETSYNC_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NetSyncAI"


def db_path(data_dir: Path) -> Path:
    return data_dir / "netsync.db"


def connect(data_dir: Path) -> sqlite3.Connection:
    """Open (creating if needed) the agent database and apply the schema."""
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path(data_dir), detect_types=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_schema(conn)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent column additions for DBs created by earlier versions."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(indexed_folders)")}
    if "access" not in cols:
        conn.execute(
            "ALTER TABLE indexed_folders ADD COLUMN access TEXT NOT NULL DEFAULT 'read'"
        )
        conn.commit()
    if "last_indexed_at" not in cols:
        conn.execute("ALTER TABLE indexed_folders ADD COLUMN last_indexed_at TEXT")
        conn.commit()
    # sync_state added in Phase 4 — CREATE IF NOT EXISTS covers it via
    # _apply_schema, nothing else needed


def _apply_schema(conn: sqlite3.Connection) -> None:
    sql = SCHEMA_PATH.read_text("utf-8")
    conn.executescript(sql)


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM agent_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO agent_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
