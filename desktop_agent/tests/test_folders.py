"""Dashboard-driven folder management + sensitive-path protection."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from file_operations.folders import FOLDER_HANDLERS, is_blocked
from file_operations.ops import AgentContext, HANDLERS, OpDenied
from indexing.indexer import search_files


@pytest.fixture
def ctx(conn):
    async def _send(raw):
        pass
    return AgentContext(conn, _send)


@pytest.fixture
def allow_tmp(monkeypatch):
    """pytest's tmp_path lives under %LOCALAPPDATA%\\Temp, which the agent
    (correctly) refuses to share. Relax only that rule for these tests."""
    import file_operations.folders as folders
    monkeypatch.setenv("APPDATA", r"Z:\not-real\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", r"Z:\not-real\Local")
    monkeypatch.setattr(folders, "_PROFILE_SECRETS",
                        tuple(p for p in folders._PROFILE_SECRETS if p != "AppData"))


async def _wait_indexed(ctx):
    for _ in range(100):
        if not ctx.indexing:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("indexing did not finish")


# ── protection rules ─────────────────────────────────────────────────────────

def test_drive_root_blocked():
    assert is_blocked(Path(Path.home().anchor))


def test_home_root_blocked():
    assert is_blocked(Path.home())


def test_appdata_and_inside_blocked():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        pytest.skip("no APPDATA")
    assert is_blocked(Path(appdata))
    assert is_blocked(Path(appdata) / "Microsoft")


def test_folder_containing_protected_location_blocked():
    # the Users folder contains every profile's AppData
    assert is_blocked(Path.home().parent)


def test_ssh_folder_blocked():
    assert is_blocked(Path.home() / ".ssh")


def test_agent_data_dir_blocked(tmp_path):
    assert is_blocked(tmp_path / "data", data_dir=tmp_path / "data")


def test_normal_folder_allowed():
    assert is_blocked(Path.home() / "Documents" / "Projects") is None


def test_temp_folder_is_protected(tmp_path):
    # tmp_path is under %LOCALAPPDATA% — must be refused
    assert is_blocked(tmp_path)


# ── tools ────────────────────────────────────────────────────────────────────

async def test_add_list_remove_folder(ctx, sample_tree, allow_tmp):
    res = await FOLDER_HANDLERS["add_folder"](
        ctx, {"path": str(sample_tree), "access": "readwrite", "label": "Project"}
    )
    assert res["label"] == "Project"
    await _wait_indexed(ctx)

    listed = (await FOLDER_HANDLERS["list_folders"](ctx, {}))["folders"]
    assert len(listed) == 1
    f = listed[0]
    assert f["access"] == "readwrite"
    assert f["file_count"] > 0 and f["total_size"] > 0
    assert f["last_indexed_at"] is not None

    # immediately browsable/searchable through the normal ops
    hits = search_files(ctx.conn, "proposal")
    assert hits and Path(hits[0]["path"]).is_file()

    await FOLDER_HANDLERS["remove_folder"](ctx, {"path": str(sample_tree)})
    assert (await FOLDER_HANDLERS["list_folders"](ctx, {}))["folders"] == []
    with pytest.raises(OpDenied):
        await HANDLERS["browse_folder"](ctx, {"path": str(sample_tree)})


async def test_add_blocked_folder_denied(ctx):
    with pytest.raises(OpDenied, match="cannot be shared"):
        await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(Path.home()), "access": "read"})


async def test_add_rejects_bad_access(ctx, sample_tree):
    with pytest.raises(OpDenied):
        await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(sample_tree), "access": "none"})


async def test_add_rejects_missing_dir(ctx, tmp_path):
    with pytest.raises(OpDenied, match="not a directory"):
        await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(tmp_path / "nope")})


async def test_set_access_downgrade_blocks_writes(ctx, sample_tree, allow_tmp):
    await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(sample_tree), "access": "readwrite"})
    await _wait_indexed(ctx)
    await FOLDER_HANDLERS["set_folder_access"](ctx, {"path": str(sample_tree), "access": "read"})
    with pytest.raises(OpDenied):
        await HANDLERS["create_folder"](ctx, {"path": str(sample_tree / "new")})


async def test_list_local_dirs_roots_and_children(ctx, sample_tree):
    roots = await FOLDER_HANDLERS["list_local_dirs"](ctx, {"path": ""})
    assert any(e["kind"] == "drive" for e in roots["entries"])

    res = await FOLDER_HANDLERS["list_local_dirs"](ctx, {"path": str(sample_tree)})
    names = {e["name"] for e in res["entries"]}
    assert "docs" in names and "src" in names
    # directory-only: file names never leak
    assert "README.md" not in names
    assert res["parent"] == str(sample_tree.resolve().parent)


async def test_list_local_dirs_marks_blocked(ctx):
    res = await FOLDER_HANDLERS["list_local_dirs"](ctx, {"path": str(Path.home())})
    appdata = next((e for e in res["entries"] if e["name"] == "AppData"), None)
    if appdata is not None:   # AppData is hidden on some systems
        assert appdata["blocked"]


async def test_search_returns_absolute_paths(ctx, sample_tree, allow_tmp):
    await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(sample_tree), "access": "read"})
    await _wait_indexed(ctx)
    for hit in search_files(ctx.conn, ""):
        assert Path(hit["path"]).is_absolute()
        assert Path(hit["path"]).exists()
