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


async def test_repairing_same_machine_resumes_device(client, auth_headers):
    # a PC reinstalling/re-pairing must resume its device record — the
    # device_id (and all shares/sessions keyed to it) survives; the new
    # pairing code's name applies as a plain rename
    first = await _create_code(client, auth_headers, "mezie")
    r1 = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": first["code"], "machine_id": "pc-abc-123"},
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()

    second = await _create_code(client, auth_headers, "de mezie")
    r2 = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": second["code"], "machine_id": "pc-abc-123",
              "agent_version": "0.4.7"},
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["device_id"] == d1["device_id"]      # same device, not a duplicate
    assert d2["device_name"] == "de mezie"         # rename applied
    assert d2["device_credential"] != d1["device_credential"]  # rotated

    # no duplicate device was minted
    r = await client.get("/api/v1/devices", headers=auth_headers)
    names = [d["name"] for d in r.json()]
    assert names == ["de mezie"]

    # the old credential no longer authenticates — rotation is real
    from app.api.deps import get_device_store
    store = get_device_store()
    assert not await store.verify_device_credential(
        d1["device_id"], d1["device_credential"])
    assert await store.verify_device_credential(
        d2["device_id"], d2["device_credential"])


async def test_repairing_same_name_resumes_device(client, auth_headers):
    # an older agent (no fingerprint) re-pairing with the same device name
    # must resume the record — same device_id, rotated credential — not
    # die on the unique (owner_id, name) constraint
    first = await _create_code(client, auth_headers, "mezie")
    r1 = await client.post("/api/v1/pairing/redeem", json={"code": first["code"]})
    assert r1.status_code == 200
    d1 = r1.json()

    second = await _create_code(client, auth_headers, "mezie")
    r2 = await client.post("/api/v1/pairing/redeem", json={"code": second["code"]})
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["device_id"] == d1["device_id"]
    assert d2["device_credential"] != d1["device_credential"]

    r = await client.get("/api/v1/devices", headers=auth_headers)
    assert [d["name"] for d in r.json()] == ["mezie"]


async def test_same_name_on_different_machine_gets_suffix(client, auth_headers):
    # a genuinely different PC with the same name gets 'name (2)' —
    # it must not take over the first device's identity
    first = await _create_code(client, auth_headers, "office-pc")
    r1 = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": first["code"], "machine_id": "machine-A"})
    assert r1.status_code == 200

    second = await _create_code(client, auth_headers, "office-pc")
    r2 = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": second["code"], "machine_id": "machine-B"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["device_id"] != r1.json()["device_id"]
    assert d2["device_name"] == "office-pc (2)"


async def test_machine_id_does_not_cross_owner(
    client, auth_headers, other_auth_headers
):
    # a second user re-pairing a PC only ever claims THEIR OWN device with
    # that fingerprint — never the first owner's
    body = await _create_code(client, auth_headers, "mezie")
    r1 = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": body["code"], "machine_id": "shared-pc"},
    )
    assert r1.status_code == 200

    body2 = await _create_code(client, other_auth_headers, "second-owner-pc")
    r2 = await client.post(
        "/api/v1/pairing/redeem",
        json={"code": body2["code"], "machine_id": "shared-pc"},
    )
    assert r2.status_code == 200
    assert r2.json()["device_id"] != r1.json()["device_id"]


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
