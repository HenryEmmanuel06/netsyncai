"""Sync-engine protection tests — a deleted sync root must END the session
on both sides without touching the peer's copy."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from protocol import Envelope, MessageType, SyncEvent, SyncOpType
from synchronization.sync_engine import SyncEngine, SyncRuntime


class FakeCtx:
    def __init__(self, conn):
        self.conn = conn
        self.sent: list[str] = []

    async def send(self, raw: str):
        self.sent.append(raw)


@pytest.fixture
def ctx(conn):
    return FakeCtx(conn)


def _engine(ctx, root, sid="s1"):
    eng = SyncEngine(ctx, "dev-1")
    eng.sessions[sid] = SyncRuntime(sid, root, "peer-1", "dev-1", "live", ctx)
    return eng


async def test_peer_root_delete_ends_sync_without_deleting(ctx, tmp_path):
    """Peer deleted the synced folder → our copy survives, session ends."""
    root = tmp_path / "shared"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.txt").write_text("keep me")
    eng = _engine(ctx, root)

    env = Envelope(type=MessageType.SYNC_EVENT, payload=SyncEvent(
        session_id="s1", op_id="op1", op=SyncOpType.RMDIR,
        rel_path=".", from_device="peer-1").model_dump())
    await eng.on_sync_event(env)

    assert "s1" not in eng.sessions
    assert root.is_dir()
    assert (root / "docs" / "a.txt").read_text() == "keep me"


async def test_local_root_delete_emits_only_root_marker(ctx, tmp_path):
    """Deleting the synced root locally must emit ONE "." marker — never
    the cascade of child deletes that would gut the peer's copy."""
    root = tmp_path / "shared"
    root.mkdir()
    eng = _engine(ctx, root)
    rt = eng.sessions["s1"]

    batch = [
        ("deleted", str(root / "a.txt"), None, False),
        ("deleted", str(root / "sub"), None, True),
        ("deleted", str(root), None, True),   # the root itself
    ]
    await eng._emit_batch(rt, batch)

    sent = [Envelope.model_validate_json(x) for x in ctx.sent]
    assert len(sent) == 1
    ev = SyncEvent.model_validate(sent[0].payload)
    assert ev.op is SyncOpType.RMDIR
    assert ev.rel_path == "."
    assert "s1" not in eng.sessions


async def test_emit_batch_dead_root_suppresses_child_deletes(ctx, tmp_path):
    """When watchdog reports the children of a root delete but not the
    root itself, the root-exists check still blocks propagation."""
    root = tmp_path / "shared"
    root.mkdir()
    shutil.rmtree(root)                      # root really is gone
    eng = _engine(ctx, root)
    rt = eng.sessions["s1"]

    await eng._emit_batch(rt, [("deleted", str(root / "a.txt"), None, False)])

    sent = [Envelope.model_validate_json(x) for x in ctx.sent]
    assert len(sent) == 1
    assert SyncEvent.model_validate(sent[0].payload).rel_path == "."
    assert "s1" not in eng.sessions
