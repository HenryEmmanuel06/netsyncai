import pytest

from app.api.pairing import PAIRING_TTL_SECONDS

pytestmark = pytest.mark.asyncio


async def _create_code(client, headers, name="HomePC"):
    r = await client.post(
        "/api/v1/pairing", json={"device_name": name}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_pairing_requires_auth(client):
    r = await client.post("/api/v1/pairing", json={"device_name": "x"})
    assert r.status_code == 401


async def test_create_pairing_returns_code(client, auth_headers):
    body = await _create_code(client, auth_headers)
    assert len(body["code"]) == 8
    assert body["expires_in_seconds"] == PAIRING_TTL_SECONDS


async def test_redeem_creates_device_and_credential(client, auth_headers):
    body = await _create_code(client, auth_headers, "Aje-Laptop")
    r = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": body["code"], "agent_version": "0.1.0"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["device_name"] == "Aje-Laptop"
    assert data["device_id"]
    assert len(data["device_credential"]) > 20

    # the new device appears in the owner's list
    r = await client.get("/api/v1/devices", headers=auth_headers)
    assert data["device_id"] in [d["id"] for d in r.json()]


async def test_redeem_invalid_code(client):
    r = await client.post("/api/v1/pairing/redeem", json={"code": "WRONG123"})
    assert r.status_code == 401


async def test_redeem_code_is_single_use(client, auth_headers):
    body = await _create_code(client, auth_headers)
    r1 = await client.post("/api/v1/pairing/redeem", json={"code": body["code"]})
    assert r1.status_code == 200
    r2 = await client.post("/api/v1/pairing/redeem", json={"code": body["code"]})
    assert r2.status_code == 401


async def test_expired_code_rejected(client, auth_headers):
    from app.api.deps import get_device_store

    store = get_device_store()
    code, _ = await store.create_pairing("anyone", "Old-PC", ttl_seconds=-1)
    r = await client.post("/api/v1/pairing/redeem", json={"code": code})
    assert r.status_code == 401


async def test_pairing_codes_isolated_per_owner(
    client, auth_headers, other_auth_headers
):
    # A code created by user A does not leak to user B's device list
    body = await _create_code(client, auth_headers)
    await client.post("/api/v1/pairing/redeem", json={"code": body["code"]})
    r = await client.get("/api/v1/devices", headers=other_auth_headers)
    assert r.json() == []
