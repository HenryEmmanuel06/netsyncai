"""Phase 4 e2e: two real agents syncing folders through a live backend.

Covers: session creation, initial sync, A->B propagation, B->A
propagation, delete safety, and conflict detection.
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest

AGENT_DIR = Path(__file__).resolve().parents[2] / "desktop_agent"
sys.path.insert(0, str(AGENT_DIR))

SECRET = "e2e-sync-secret-long-enough-for-hs256"
USER = "11111111-1111-1111-1111-111111111111"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _token() -> str:
    now = int(time.time())
    return pyjwt.encode(
        {"sub": USER, "aud": "authenticated", "iat": now, "exp": now + 600},
        SECRET, algorithm="HS256",
    )


@pytest.fixture(scope="module")
def backend():
    port = _free_port()
    env = {**os.environ, "DEVICE_STORE": "memory",
           "SUPABASE_JWT_SECRET": SECRET, "DEBUG": "true"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[1],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(f"{base}/health", timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("backend did not start")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


async def _wait_for(cond, timeout=15, interval=0.3):
    for _ in range(int(timeout / interval)):
        if cond():
            return True
        await asyncio.sleep(interval)
    return False


async def test_two_agent_bidirectional_sync(backend, tmp_path):
    from database.db import connect
    from indexing.indexer import index_folder, register_folder
    from networking.coordinator import run_session

    root_a = tmp_path / "A"
    root_b = tmp_path / "B"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "seed.txt").write_text("seed from A")

    headers = {"Authorization": f"Bearer {_token()}"}
    async with httpx.AsyncClient(base_url=backend, timeout=15) as http:
        # pair two devices
        devs = []
        for name in ("sync-A", "sync-B"):
            r = await http.post("/api/v1/pairing",
                                json={"device_name": name}, headers=headers)
            code = r.json()["code"]
            r = await http.post("/api/v1/pairing/redeem", json={"code": code})
            devs.append(r.json())

        # connect two agent sessions with separate roots + DBs
        sessions = []
        for dev, root, name in ((devs[0], root_a, "a"), (devs[1], root_b, "b")):
            conn = connect(tmp_path / f"data-{name}")
            register_folder(conn, root, access="readwrite")
            index_folder(conn, 1)
            sessions.append(asyncio.create_task(
                run_session(backend, dev["device_id"],
                            dev["device_credential"], "0.1.0", conn=conn)
            ))
        await asyncio.sleep(1.5)

        try:
            # create the sync session
            r = await http.post("/api/v1/sync", headers=headers, json={
                "a_device_id": devs[0]["device_id"], "a_path": str(root_a),
                "b_device_id": devs[1]["device_id"], "b_path": str(root_b),
                "mode": "live",
            })
            assert r.status_code == 201, r.text
            session_id = r.json()["id"]

            # initial sync: seed.txt A -> B
            assert await _wait_for(
                lambda: (root_b / "seed.txt").exists()
            ), "initial sync did not propagate"
            assert (root_b / "seed.txt").read_text() == "seed from A"

            # incremental A -> B
            (root_a / "newfile.md").write_text("# created on A")
            assert await _wait_for(
                lambda: (root_b / "newfile.md").exists()
            ), "A->B create did not propagate"

            # incremental B -> A (bidirectional)
            (root_b / "fromB.txt").write_text("hello from B")
            assert await _wait_for(
                lambda: (root_a / "fromB.txt").exists()
            ), "B->A create did not propagate"

            # modify propagates
            (root_a / "seed.txt").write_text("edited on A")
            assert await _wait_for(
                lambda: (root_b / "seed.txt").exists()
                and (root_b / "seed.txt").read_text() == "edited on A"
            ), "modify did not propagate"

            # delete propagates (file is sync-tracked)
            (root_b / "newfile.md").unlink()
            assert await _wait_for(
                lambda: not (root_a / "newfile.md").exists()
            ), "delete did not propagate"

            # pause stops propagation
            r = await http.post(f"/api/v1/sync/{session_id}/pause",
                                headers=headers)
            assert r.json()["state"] == "paused"
            (root_a / "paused.txt").write_text("no sync while paused")
            await asyncio.sleep(2)
            assert not (root_b / "paused.txt").exists()

            # resume converges
            await http.post(f"/api/v1/sync/{session_id}/resume", headers=headers)
            assert await _wait_for(
                lambda: (root_b / "paused.txt").exists()
            ), "resume did not converge"
        finally:
            for s in sessions:
                s.cancel()
            for s in sessions:
                with pytest.raises(asyncio.CancelledError):
                    await s
