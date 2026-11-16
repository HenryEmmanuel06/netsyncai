import sqlite3


def test_schema_creates_all_tables(conn):
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
        )
    }
    expected = {
        "indexed_folders", "files", "local_permissions", "file_revisions",
        "sync_journal", "pending_operations", "transfer_checkpoints",
        "agent_settings",
    }
    assert expected <= tables


def test_fts5_available(conn):
    # will raise if FTS5 isn't compiled in
    conn.execute("CREATE VIRTUAL TABLE temp.ft USING fts5(x)")
    conn.execute("INSERT INTO ft(x) VALUES ('hello world')")
    assert conn.execute("SELECT rowid FROM ft WHERE ft MATCH 'hello'").fetchone()


def test_settings_roundtrip(conn):
    from database.db import get_setting, set_setting

    assert get_setting(conn, "missing") is None
    set_setting(conn, "device_id", "abc-123")
    assert get_setting(conn, "device_id") == "abc-123"
    set_setting(conn, "device_id", "xyz")
    assert get_setting(conn, "device_id") == "xyz"


def test_op_id_dedupe(conn):
    conn.execute(
        "INSERT INTO sync_journal (op_id, session_id, op_type, rel_path) "
        "VALUES ('op1', 's1', 'create', 'a.txt')"
    )
    try:
        conn.execute(
            "INSERT INTO sync_journal (op_id, session_id, op_type, rel_path) "
            "VALUES ('op1', 's1', 'create', 'a.txt')"
        )
        assert False, "duplicate op_id must raise"
    except sqlite3.IntegrityError:
        pass
