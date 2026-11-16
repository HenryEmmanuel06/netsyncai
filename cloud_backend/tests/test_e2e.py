"""Full-stack e2e: real uvicorn process + real agent session over WSS.

Exercises the complete Phase 3 path: REST → command.dispatch → agent ops
→ command.result → REST response, plus a download transfer.
"""

import asyncio
import hashlib
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest

AGENT_DIR = Path(__file__).resolve().parents[2] / "desktop_agent"
sys.path.insert(0, str(AGENT_DIR))

SECRET = "e2e-test-secret-long-enough-for-hs256"
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
    env = {
        **os.environ,
        "DEVICE_STORE": "memory",
        "SUPABASE_JWT_SECRET": SECRET,
        "DEBUG": "true",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


@pytest.fixture
def agent_files(tmp_path):
    root = tmp_path / "shared"
    (root / "sub").mkdir(parents=True)
    (root / "hello.txt").write_text("hello netsync")
    (root / "sub" / "doc.pdf").write_bytes(b"%PDF fake")
    return root


async def test_full_remote_file_flow(backend, agent_files):
    """Pair → connect agent → browse/search/rename/download via REST."""
    from database.db import connect
    from indexing.indexer import index_folder, register_folder
    from networking.coordinator import run_session

    headers = {"Authorization": f"Bearer {_token()}"}
    async with httpx.AsyncClient(base_url=backend, timeout=10) as http:
        # pair
        r = await http.post("/api/v1/pairing",
                            json={"device_name": "e2e-pc"}, headers=headers)
        code = r.json()["code"]
        r = await http.post("/api/v1/pairing/redeem", json={"code": code})
        dev = r.json()

        # agent session with a real indexed folder
        conn = connect(agent_files.parent / "agentdata")
        register_folder(conn, agent_files, access="readwrite")
        index_folder(conn, 1)
        session = asyncio.create_task(
            run_session(backend, dev["device_id"], dev["device_credential"], "0.1.0", conn=conn)
        )
        await asyncio.sleep(1.5)  # handshake
        try:
            # device should be online
            r = await http.get("/api/v1/devices", headers=headers)
            assert r.json()[0]["status"] == "online"

            # browse roots
            r = await http.get(
                f"/api/v1/devices/{dev['device_id']}/browse", headers=headers
            )
            assert r.status_code == 200, r.text
            assert r.json()["roots"][0]["path"] == str(agent_files.resolve())
            assert r.json()["roots"][0]["access"] == "readwrite"

            # browse dir
            r = await http.get(
                f"/api/v1/devices/{dev['device_id']}/browse",
                params={"path": str(agent_files)}, headers=headers,
            )
            names = {e["name"] for e in r.json()["entries"]}
            assert {"hello.txt", "sub"} <= names

            # search
            r = await http.get(
                f"/api/v1/devices/{dev['device_id']}/search",
                params={"q": "hello"}, headers=headers,
            )
            assert r.json()["results"][0]["name"] == "hello.txt"

            # download — real chunked transfer over WSS relay
            r = await http.get(
                f"/api/v1/devices/{dev['device_id']}/download",
                params={"path": str(agent_files / "hello.txt")}, headers=headers,
            )
            assert r.status_code == 200
            assert r.content == b"hello netsync"
            assert r.headers["X-Content-Sha256"] == hashlib.sha256(
                b"hello netsync"
            ).hexdigest()

            # rename via remote op
            r = await http.post(
                f"/api/v1/devices/{dev['device_id']}/rename",
                json={"path": str(agent_files / "hello.txt"), "new_name": "renamed.txt"},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert (agent_files / "renamed.txt").exists()

            # upload — browser body → relay → agent writes + verifies
            payload = b"uploaded-by-e2e " * 3000
            r = await http.post(
                f"/api/v1/devices/{dev['device_id']}/upload",
                params={"path": str(agent_files / "uploaded.bin")},
                files={"file": ("uploaded.bin", payload)},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            res = r.json()
            assert res["sha256"] == hashlib.sha256(payload).hexdigest()
            assert Path(res["written"]).read_bytes() == payload

            # unauthorized path → 409 from the agent's OpDenied
            r = await http.post(
                f"/api/v1/devices/{dev['device_id']}/rename",
                json={"path": str(agent_files.parent), "new_name": "evil"},
                headers=headers,
            )
            assert r.status_code == 409
        finally:
            session.cancel()
            with pytest.raises(asyncio.CancelledError):
                await session
