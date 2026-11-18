"""Stable per-machine, per-user identifier.

Stored in the HKCU registry so it survives reinstalls, upgrades and even a
wiped data directory — pairing the same PC again lands on the SAME cloud
device instead of minting a duplicate. A per-user (not per-machine) key is
deliberate: two Windows accounts on one PC are two NetSync devices.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid

log = logging.getLogger("netsync.machine")

_REG_KEY = r"Software\NetSyncAI"
_REG_NAME = "machine_id"


def _registry_id() -> str | None:
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as k:
            try:
                return winreg.QueryValueEx(k, _REG_NAME)[0]
            except FileNotFoundError:
                mid = uuid.uuid4().hex
                winreg.SetValueEx(k, _REG_NAME, 0, winreg.REG_SZ, mid)
                return mid
    except Exception:
        log.exception("registry machine_id unavailable")
        return None


def machine_id(conn: sqlite3.Connection | None = None) -> str:
    """The machine's stable id. Empty string when nothing can persist one —
    the backend then treats the pair as a brand-new device."""
    mid = _registry_id()
    if mid:
        return mid
    if conn is None:
        return ""
    from database.db import get_setting, set_setting
    mid = get_setting(conn, "machine_id") or ""
    if not mid:
        mid = uuid.uuid4().hex
        set_setting(conn, "machine_id", mid)
    return mid
