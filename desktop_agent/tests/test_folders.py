"""Dashboard-driven folder management + sensitive-path protection."""

import asyncio
import os
import shutil
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


def test_index_progress_reports_counts(conn, tmp_path, allow_tmp):
    """Progress dict fills in done/total so the UI can show a percentage."""
    from indexing.indexer import index_folder, register_folder
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x")
    fid = register_folder(conn, tmp_path, label="t", access="read")
    progress: dict = {"done": 0, "total": None}
    stats = index_folder(conn, fid, progress=progress)
    # every file the pre-scan counted ends up processed by the index walk
    assert progress["done"] == progress["total"]
    assert stats.added == progress["total"]


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


async def test_list_folders_prunes_deleted_roots(ctx, sample_tree, allow_tmp):
    """A shared folder deleted in Explorer stops showing on next list."""
    await FOLDER_HANDLERS["add_folder"](
        ctx, {"path": str(sample_tree), "access": "read"})
    shutil.rmtree(sample_tree)
    listed = (await FOLDER_HANDLERS["list_folders"](ctx, {}))["folders"]
    assert listed == []


async def test_add_blocked_folder_denied(ctx):
    with pytest.raises(OpDenied, match="cannot be shared"):
        await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(Path.home()), "access": "read"})


async def test_add_rejects_bad_access(ctx, sample_tree):
    with pytest.raises(OpDenied):
        await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(sample_tree), "access": "none"})


async def test_add_rejects_missing_dir(ctx, tmp_path):
    with pytest.raises(OpDenied, match="not a file or folder"):
        await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(tmp_path / "nope")})


async def test_add_folder_create_flag_makes_dir(ctx, tmp_path, allow_tmp):
    """create=true makes a brand-new folder (sync-into-Downloads accept)."""
    target = tmp_path / "NetSync - Photos"
    r = await FOLDER_HANDLERS["add_folder"](ctx, {
        "path": str(target), "access": "readwrite", "create": True,
    })
    assert target.is_dir()
    assert r["access"] == "readwrite"
    listed = (await FOLDER_HANDLERS["list_folders"](ctx, {}))["folders"]
    assert [f["path"] for f in listed] == [r["path"]]


async def test_add_folder_unique_avoids_collisions(ctx, tmp_path, allow_tmp):
    """Two incoming 'methic' syncs must land in different folders — never
    silently merge into one directory."""
    downloads = tmp_path / "Downloads"
    r1 = await FOLDER_HANDLERS["add_folder"](ctx, {
        "path": str(downloads / "methic"), "access": "readwrite",
        "create": True, "unique": True,
    })
    r2 = await FOLDER_HANDLERS["add_folder"](ctx, {
        "path": str(downloads / "methic"), "access": "readwrite",
        "create": True, "unique": True,
    })
    assert r1["path"] != r2["path"]
    assert Path(r1["path"]).name == "methic"
    assert Path(r2["path"]).name == "methic (2)"
    assert Path(r2["path"]).is_dir()
    assert r2["label"] == "methic (2)"

    # a name already registered but missing on disk also bumps —
    # syncing into a "dead" share path would resurrect the wrong folder
    shutil.rmtree(downloads / "methic")
    r3 = await FOLDER_HANDLERS["add_folder"](ctx, {
        "path": str(downloads / "methic"), "access": "readwrite",
        "create": True, "unique": True,
    })
    assert Path(r3["path"]).name == "methic (3)"


async def test_add_folder_unique_respects_unregistered_dirs(ctx, tmp_path,
                                                            allow_tmp):
    # the path exists on disk but isn't a NetSync share — reusing it would
    # inject synced files into a personal folder, so take the next free name
    personal = tmp_path / "Downloads" / "methic"
    personal.mkdir(parents=True)
    r = await FOLDER_HANDLERS["add_folder"](ctx, {
        "path": str(personal), "access": "readwrite",
        "create": True, "unique": True,
    })
    assert Path(r["path"]).name == "methic (2)"


async def test_add_file_share(ctx, sample_tree, allow_tmp):
    """A single file can be shared — it's registered and indexed as itself."""
    f = sample_tree / "README.md"
    r = await FOLDER_HANDLERS["add_folder"](ctx, {"path": str(f), "access": "read"})
    assert r["path"] == str(f.resolve())
    assert r["label"] == "README.md"


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
