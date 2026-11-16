-- NetSync agent-local SQLite schema.
-- Lives under %LOCALAPPDATA%\NetSyncAI\netsync.db — never inside the exe.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Folders the LOCAL user explicitly chose to index/share.
CREATE TABLE IF NOT EXISTS indexed_folders (
  id         INTEGER PRIMARY KEY,
  path       TEXT NOT NULL UNIQUE,      -- absolute, normalized
  label      TEXT NOT NULL DEFAULT '',
  access     TEXT NOT NULL DEFAULT 'read',  -- none|read|readwrite (remote ops)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_indexed_at TEXT
);

-- Stable file identity: file_id survives renames/moves.
CREATE TABLE IF NOT EXISTS files (
  id         INTEGER PRIMARY KEY,
  folder_id  INTEGER NOT NULL REFERENCES indexed_folders(id) ON DELETE CASCADE,
  file_id    TEXT NOT NULL UNIQUE,      -- uuid assigned at first sighting
  rel_path   TEXT NOT NULL,
  name       TEXT NOT NULL,
  ext        TEXT NOT NULL DEFAULT '',
  size       INTEGER NOT NULL DEFAULT 0,
  mtime      REAL NOT NULL DEFAULT 0,
  sha256     TEXT,
  deleted    INTEGER NOT NULL DEFAULT 0,
  UNIQUE (folder_id, rel_path)
);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
  name, rel_path, ext,
  content = 'files', content_rowid = 'id'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
  INSERT INTO files_fts(rowid, name, rel_path, ext)
    VALUES (new.id, new.name, new.rel_path, new.ext);
END;
CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
  INSERT INTO files_fts(files_fts, rowid, name, rel_path, ext)
    VALUES ('delete', old.id, old.name, old.rel_path, old.ext);
END;
CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
  INSERT INTO files_fts(files_fts, rowid, name, rel_path, ext)
    VALUES ('delete', old.id, old.name, old.rel_path, old.ext);
  INSERT INTO files_fts(rowid, name, rel_path, ext)
    VALUES (new.id, new.name, new.rel_path, new.ext);
END;

-- Permissions mirrored from the coordinator; agent is final authority.
CREATE TABLE IF NOT EXISTS local_permissions (
  id                 INTEGER PRIMARY KEY,
  folder_id          INTEGER NOT NULL REFERENCES indexed_folders(id) ON DELETE CASCADE,
  subject_user_id    TEXT,
  subject_device_id  TEXT,
  role               TEXT NOT NULL DEFAULT 'viewer',
  permissions_granted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_revisions (
  id           INTEGER PRIMARY KEY,
  file_row_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
  sha256       TEXT NOT NULL,
  size         INTEGER NOT NULL,
  mtime        REAL NOT NULL,
  op_id        TEXT,                       -- stable op id (dedupe sync loops)
  origin       TEXT NOT NULL DEFAULT 'local',
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS file_revisions_file_idx ON file_revisions (file_row_id, id DESC);

CREATE TABLE IF NOT EXISTS sync_journal (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  op_id      TEXT NOT NULL UNIQUE,        -- dedupe: never apply same op twice
  session_id TEXT NOT NULL,
  op_type    TEXT NOT NULL,               -- create|modify|delete|rename
  rel_path   TEXT NOT NULL,
  payload    TEXT NOT NULL DEFAULT '{}',  -- json
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS sync_journal_session_idx ON sync_journal (session_id, seq);

CREATE TABLE IF NOT EXISTS pending_operations (
  id         INTEGER PRIMARY KEY,
  op_id      TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  op_type    TEXT NOT NULL,
  payload    TEXT NOT NULL DEFAULT '{}',
  retries    INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transfer_checkpoints (
  transfer_id TEXT PRIMARY KEY,
  direction   TEXT NOT NULL,              -- send|recv
  peer_device TEXT NOT NULL,
  local_path  TEXT NOT NULL,
  bytes_done  INTEGER NOT NULL DEFAULT 0,
  total_bytes INTEGER NOT NULL DEFAULT 0,
  sha256      TEXT,
  state       TEXT NOT NULL DEFAULT 'active',
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Last-synced state per file per session — the "base" version used for
-- conflict detection (local sha != base && remote sha != base => conflict).
CREATE TABLE IF NOT EXISTS sync_state (
  session_id TEXT NOT NULL,
  rel_path   TEXT NOT NULL,
  sha256     TEXT NOT NULL,
  mtime      REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (session_id, rel_path)
);

CREATE TABLE IF NOT EXISTS agent_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
