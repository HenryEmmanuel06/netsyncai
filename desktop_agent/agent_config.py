"""Build/runtime configuration resolution for the agent.

The shipped exe can't rely on a .env file. Priority order:

  1. explicit --coordinator / --data-dir CLI flags
  2. values saved at pair time (agent_settings table)
  3. NETSYNC_COORDINATOR_URL / NETSYNC_DATA_DIR env vars
  4. build_config.json bundled into the exe by PyInstaller — THIS is how
     a released agent learns the production backend URL. Edit this file
     (or pass --coordinator) for local dev; the release build sets it to
     the Render URL before running pyinstaller.
  5. hardcoded localhost fallback
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

AGENT_VERSION = "0.4.7"


def _config_path() -> Path | None:
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "build_config.json"  # type: ignore[attr-defined]
        if p.exists():
            return p
    p = Path(__file__).parent / "build_config.json"
    return p if p.exists() else None


def bundled_config() -> dict:
    p = _config_path()
    if p is None:
        return {}
    try:
        # utf-8-sig: tolerate the BOM some Windows editors/shells write
        return json.loads(p.read_text("utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def default_coordinator() -> str:
    if url := os.environ.get("NETSYNC_COORDINATOR_URL"):
        return url
    return bundled_config().get("coordinator_url", "http://localhost:8000")


def dashboard_url() -> str:
    if url := os.environ.get("NETSYNC_DASHBOARD_URL"):
        return url
    return bundled_config().get("dashboard_url", "http://localhost:3000")


def default_data_dir() -> Path | None:
    """Returns the env override or None (caller falls back to %LOCALAPPDATA%)."""
    if d := os.environ.get("NETSYNC_DATA_DIR"):
        return Path(d)
    return None
