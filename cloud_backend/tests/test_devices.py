import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, headers, name="Aje-Laptop"):
    r = await client.post(
        "/api/v1/devices",
        json={"name": name, "platform": "windows", "agent_version": "0.1.0"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_register_and_list(client, auth_headers):
    created = await _register(client, auth_headers)
    assert created["name"] == "Aje-Laptop"
    assert created["status"] == "offline"

    r = await client.get("/api/v1/devices", headers=auth_headers)
    assert r.status_code == 200
    assert [d["id"] for d in r.json()] == [created["id"]]


async def test_owner_isolation(client, auth_headers, other_auth_headers):
    created = await _register(client, auth_headers)

    r = await client.get("/api/v1/devices", headers=other_auth_headers)
    assert r.json() == []

    r = await client.get(
        f"/api/v1/devices/{created['id']}", headers=other_auth_headers
    )
    assert r.status_code == 404  # don't leak existence


async def test_status_update(client, auth_headers):
    created = await _register(client, auth_headers)
    r = await client.patch(
        f"/api/v1/devices/{created['id']}/status",
        json={"status": "online"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "online"
    assert r.json()["last_seen_at"] is not None


async def test_invalid_status_rejected(client, auth_headers):
    created = await _register(client, auth_headers)
    r = await client.patch(
        f"/api/v1/devices/{created['id']}/status",
        json={"status": "sleeping"},
        headers=auth_headers,
    )
    assert r.status_code == 422


async def test_revoke(client, auth_headers):
    created = await _register(client, auth_headers)
    await client.patch(
        f"/api/v1/devices/{created['id']}/status",
        json={"status": "online"},
        headers=auth_headers,
    )
    r = await client.post(
        f"/api/v1/devices/{created['id']}/revoke", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["status"] == "offline"
    assert r.json()["revoked_at"] is not None


async def test_revoke_other_users_device_fails(
    client, auth_headers, other_auth_headers
):
    created = await _register(client, auth_headers)
    r = await client.post(
        f"/api/v1/devices/{created['id']}/revoke", headers=other_auth_headers
    )
    assert r.status_code == 404


async def test_empty_name_rejected(client, auth_headers):
    r = await client.post(
        "/api/v1/devices", json={"name": ""}, headers=auth_headers
    )
    assert r.status_code == 422
