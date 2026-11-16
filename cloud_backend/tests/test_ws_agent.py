"""WebSocket agent tests — sync TestClient handles WS endpoints cleanly."""

import json
import time
import uuid

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_device_store
from app.main import app
from app.protocol import AgentHello, Envelope, MessageType
from tests.conftest import TEST_SECRET, TEST_USER


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    now = int(time.time())
    token = pyjwt.encode(
        {"sub": TEST_USER, "aud": "authenticated", "iat": now, "exp": now + 3600},
        TEST_SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _pair_device(client, headers, name="WS-PC"):
    r = client.post("/api/v1/pairing", json={"device_name": name}, headers=headers)
    code = r.json()["code"]
    r = client.post("/api/v1/pairing/redeem", json={"code": code})
    return r.json()


def _hello(device_id, credential, status="online"):
    return Envelope(
        type=MessageType.AGENT_HELLO,
        payload=AgentHello(
            device_id=device_id,
            device_credential=credential,
            agent_version="0.1.0",
            status=status,
        ).model_dump(),
    ).model_dump_json()


def _read_envelope(ws):
    return Envelope.model_validate_json(ws.receive_text())


def test_hello_auth_connects_and_sets_online(client, auth_headers):
    dev = _pair_device(client, auth_headers)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(dev["device_id"], dev["device_credential"]))
        ack = _read_envelope(ws)
        assert ack.type is MessageType.PONG

    r = client.get("/api/v1/devices", headers=auth_headers)
    d = next(d for d in r.json() if d["id"] == dev["device_id"])
    assert d["status"] == "offline"  # ws closed → back offline


def test_online_during_connection(client, auth_headers):
    dev = _pair_device(client, auth_headers)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(dev["device_id"], dev["device_credential"]))
        _read_envelope(ws)
        r = client.get("/api/v1/devices", headers=auth_headers)
        d = next(d for d in r.json() if d["id"] == dev["device_id"])
        assert d["status"] == "online"


def test_bad_credential_rejected(client, auth_headers):
    dev = _pair_device(client, auth_headers)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(dev["device_id"], "wrong-credential"))
        env = _read_envelope(ws)
        assert env.type is MessageType.ERROR
        assert env.payload["code"] == "auth_failed"


def test_unknown_device_rejected(client):
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(str(uuid.uuid4()), "anything"))
        env = _read_envelope(ws)
        assert env.payload["code"] == "auth_failed"


def test_revoked_device_rejected(client, auth_headers):
    dev = _pair_device(client, auth_headers)
    client.post(f"/api/v1/devices/{dev['device_id']}/revoke", headers=auth_headers)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(dev["device_id"], dev["device_credential"]))
        env = _read_envelope(ws)
        assert env.payload["code"] == "revoked"


def test_garbage_first_message_rejected(client):
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text("not json at all")
        env = _read_envelope(ws)
        assert env.type is MessageType.ERROR


def test_ping_pong_heartbeat(client, auth_headers):
    dev = _pair_device(client, auth_headers)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(dev["device_id"], dev["device_credential"]))
        _read_envelope(ws)
        ws.send_text(Envelope(type=MessageType.PING).model_dump_json())
        assert _read_envelope(ws).type is MessageType.PONG


def test_presence_update_changes_status(client, auth_headers):
    dev = _pair_device(client, auth_headers)
    with client.websocket_connect("/ws/agent") as ws:
        ws.send_text(_hello(dev["device_id"], dev["device_credential"]))
        _read_envelope(ws)
        ws.send_text(Envelope(
            type=MessageType.PRESENCE_UPDATE,
            payload={"device_id": dev["device_id"], "status": "busy"},
        ).model_dump_json())
        r = client.get("/api/v1/devices", headers=auth_headers)
        d = next(d for d in r.json() if d["id"] == dev["device_id"])
        assert d["status"] == "busy"
