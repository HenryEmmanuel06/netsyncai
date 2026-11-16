"""Agent networking tests — spins up a real local WS server as a fake
coordinator and verifies the handshake/message protocol end to end."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from networking.coordinator import (
    CredentialRejected,
    backoff_delays,
    run_forever,
    run_session,
    ws_url_for,
)
from protocol import Envelope, MessageType


def test_ws_url_for():
    assert ws_url_for("http://localhost:8000") == "ws://localhost:8000/ws/agent"
    assert ws_url_for("https://api.example.com") == "wss://api.example.com/ws/agent"
    assert ws_url_for("http://localhost:8000/") == "ws://localhost:8000/ws/agent"


def test_backoff_grows_and_caps():
    it = backoff_delays()
    vals = [next(it) for _ in range(20)]
    assert vals[0] == 1.0
    assert all(v <= 60.0 for v in vals)
    # jittered exponential: later values trend upward but never exceed cap
    assert vals[10] > vals[0]


async def _serve(handler):
    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"ws://127.0.0.1:{port}"


async def test_run_session_handshake_and_disconnect():
    received_hello = {}

    async def fake_coordinator(ws):
        raw = await ws.recv()
        env = Envelope.model_validate_json(raw)
        received_hello.update(env.payload)
        assert env.type is MessageType.AGENT_HELLO
        await ws.send(Envelope(type=MessageType.PONG, payload={"session": "ready"}).model_dump_json())
        await ws.close()

    server, url = await _serve(fake_coordinator)
    try:
        base = url.replace("ws://", "http://")
        await run_session(base, "dev-1", "cred-1", "0.1.0")
        assert received_hello["device_id"] == "dev-1"
        assert received_hello["device_credential"] == "cred-1"
    finally:
        server.close()
        await server.wait_closed()


async def test_run_session_rejected_handshake():
    async def bad_coordinator(ws):
        await ws.recv()
        await ws.send(Envelope(
            type=MessageType.ERROR,
            payload={"code": "auth_failed", "message": "bad credential"},
        ).model_dump_json())
        await ws.close()

    server, url = await _serve(bad_coordinator)
    try:
        base = url.replace("ws://", "http://")
        with pytest.raises(CredentialRejected, match="bad credential"):
            await run_session(base, "dev-1", "bad-cred", "0.1.0")
    finally:
        server.close()
        await server.wait_closed()


async def test_run_forever_stops_when_device_revoked():
    """A revoked device must not reconnect forever — it surfaces once so
    the desktop app can ask the user to pair again."""
    attempts = 0
    states = []

    async def revoked_coordinator(ws):
        nonlocal attempts
        attempts += 1
        await ws.recv()
        await ws.send(Envelope(
            type=MessageType.ERROR,
            payload={"code": "revoked", "message": "device has been revoked"},
        ).model_dump_json())
        await ws.close()

    server, url = await _serve(revoked_coordinator)
    try:
        base = url.replace("ws://", "http://")
        with pytest.raises(CredentialRejected):
            await asyncio.wait_for(
                run_forever(base, "dev-1", "cred", "0.2.0",
                            on_status=lambda s, d=None: states.append(s)),
                timeout=5,
            )
        assert attempts == 1
        assert states == ["connecting", "rejected"]
    finally:
        server.close()
        await server.wait_closed()


async def test_agent_answers_server_ping():
    pong_seen = asyncio.Event()

    async def pinging_coordinator(ws):
        await ws.recv()  # hello
        await ws.send(Envelope(type=MessageType.PONG).model_dump_json())
        await ws.send(Envelope(type=MessageType.PING).model_dump_json())
        async for raw in ws:
            env = Envelope.model_validate_json(raw)
            if env.type is MessageType.PONG:
                pong_seen.set()
        # when client closes after server close

    server, url = await _serve(pinging_coordinator)
    try:
        base = url.replace("ws://", "http://")
        task = asyncio.create_task(run_session(base, "dev-1", "cred", "0.1.0"))
        await asyncio.wait_for(pong_seen.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        server.close()
        await server.wait_closed()


async def test_command_dispatch_returns_not_implemented():
    result = {}

    async def dispatching_coordinator(ws):
        await ws.recv()  # hello
        await ws.send(Envelope(type=MessageType.PONG).model_dump_json())
        await ws.send(Envelope(
            type=MessageType.COMMAND_DISPATCH,
            payload={"task_id": "t1", "step_id": "s1", "tool": "search_files", "args": {}},
        ).model_dump_json())
        async for raw in ws:
            env = Envelope.model_validate_json(raw)
            if env.type is MessageType.COMMAND_RESULT:
                result.update(env.payload)
                break
        await ws.close()

    server, url = await _serve(dispatching_coordinator)
    try:
        base = url.replace("ws://", "http://")
        await asyncio.wait_for(
            run_session(base, "dev-1", "cred", "0.1.0"), timeout=5
        )
        assert result["ok"] is False
        assert "not available" in result["error"]
    finally:
        server.close()
        await server.wait_closed()
