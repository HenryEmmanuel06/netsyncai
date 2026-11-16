"""Owner-only folder management, pairing preview, activity feed, revocation."""

import pytest

from tests.conftest import OTHER_USER

pytestmark = pytest.mark.asyncio


async def _device(client, headers, name="PC"):
    r = await client.post("/api/v1/devices", json={"name": name}, headers=headers)
    return r.json()["id"]


async def test_folder_routes_require_auth(client):
    for method, url in [
        ("get", "/api/v1/devices/x/folders"),
        ("get", "/api/v1/devices/x/local-dirs"),
        ("post", "/api/v1/devices/x/folders"),
    ]:
        r = await getattr(client, method)(url)
        assert r.status_code == 401


async def test_folders_offline_device_409(client, auth_headers):
    dev = await _device(client, auth_headers)
    r = await client.get(f"/api/v1/devices/{dev}/folders", headers=auth_headers)
    assert r.status_code == 409
    assert "offline" in r.json()["detail"]["error"]


async def test_folders_are_owner_only_even_with_grant(
    client, auth_headers, other_auth_headers
):
    """A collaborator with full grant bits still can't add/list folders or
    browse the PC's directory tree."""
    dev = await _device(client, auth_headers)
    r = await client.post("/api/v1/sharing", headers=auth_headers,
                          json={"device_id": dev, "root_path": r"C:\shared"})
    await client.post(f"/api/v1/sharing/{r.json()['id']}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 2047})
    for method, url, body in [
        ("get", f"/api/v1/devices/{dev}/folders", None),
        ("get", f"/api/v1/devices/{dev}/local-dirs", None),
        ("post", f"/api/v1/devices/{dev}/folders", {"path": r"C:\x", "access": "read"}),
    ]:
        kw = {"headers": other_auth_headers}
        if body:
            kw["json"] = body
        r = await getattr(client, method)(url, **kw)
        assert r.status_code == 404, url


async def test_add_folder_validates_access(client, auth_headers):
    dev = await _device(client, auth_headers)
    r = await client.post(f"/api/v1/devices/{dev}/folders", headers=auth_headers,
                          json={"path": r"C:\x", "access": "everything"})
    assert r.status_code == 422


async def test_pairing_preview_shows_account_without_consuming(client, auth_headers):
    r = await client.post("/api/v1/pairing", json={"device_name": "Laptop"},
                          headers=auth_headers)
    code = r.json()["code"]
    for _ in range(2):  # preview is repeatable
        r = await client.get("/api/v1/pairing/preview", params={"code": code})
        assert r.status_code == 200
        assert r.json()["device_name"] == "Laptop"
        assert r.json()["owner_email"].endswith("@example.com")
    r = await client.post("/api/v1/pairing/redeem", json={"code": code})
    assert r.status_code == 200
    r = await client.get("/api/v1/pairing/preview", params={"code": code})
    assert r.status_code == 401  # consumed


async def test_pairing_preview_invalid_code(client):
    r = await client.get("/api/v1/pairing/preview", params={"code": "ZZZZZZZZ"})
    assert r.status_code == 401


async def test_activity_feed_records_pairing_and_is_private(
    client, auth_headers, other_auth_headers
):
    r = await client.post("/api/v1/pairing", json={"device_name": "Desk"},
                          headers=auth_headers)
    await client.post("/api/v1/pairing/redeem", json={"code": r.json()["code"]})
    r = await client.get("/api/v1/activity", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()[0]["action"] == "device.paired"
    assert r.json()[0]["target"] == "Desk"
    r = await client.get("/api/v1/activity", headers=other_auth_headers)
    assert r.json() == []


async def test_revoke_records_activity(client, auth_headers):
    dev = await _device(client, auth_headers)
    r = await client.post(f"/api/v1/devices/{dev}/revoke", headers=auth_headers)
    assert r.status_code == 200
    acts = (await client.get("/api/v1/activity", headers=auth_headers)).json()
    assert acts[0]["action"] == "device.removed"
