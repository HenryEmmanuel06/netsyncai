"""Tags, preferences, and the fan-out search."""

import pytest

from tests.conftest import OTHER_USER

pytestmark = pytest.mark.asyncio


async def _device(client, headers, name="PC"):
    r = await client.post("/api/v1/devices", json={"name": name}, headers=headers)
    return r.json()["id"]


async def test_tags_are_per_user(client, auth_headers, other_auth_headers):
    dev = await _device(client, auth_headers)
    r = await client.put(f"/api/v1/devices/{dev}/tags", headers=auth_headers,
                         json={"path": r"C:\f\a.pdf", "tag": "urgent"})
    assert r.status_code == 201
    r = await client.get(f"/api/v1/devices/{dev}/tags", headers=auth_headers)
    assert r.json() == {r"C:\f\a.pdf": ["urgent"]}
    # a user with no grant can't see the device at all
    r = await client.get(f"/api/v1/devices/{dev}/tags", headers=other_auth_headers)
    assert r.status_code == 404
    await client.delete(f"/api/v1/devices/{dev}/tags", headers=auth_headers,
                        params={"path": r"C:\f\a.pdf", "tag": "urgent"})
    r = await client.get(f"/api/v1/devices/{dev}/tags", headers=auth_headers)
    assert r.json() == {}


async def test_collaborator_has_own_tag_map(client, auth_headers, other_auth_headers):
    dev = await _device(client, auth_headers)
    share = (await client.post("/api/v1/sharing", headers=auth_headers,
                               json={"device_id": dev, "root_path": r"C:\f"})
             ).json()
    await client.post(f"/api/v1/sharing/{share['id']}/grants", headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 1})
    await client.put(f"/api/v1/devices/{dev}/tags", headers=other_auth_headers,
                     json={"path": r"C:\f\a.pdf", "tag": "to-read"})
    mine = await client.get(f"/api/v1/devices/{dev}/tags", headers=auth_headers)
    theirs = await client.get(f"/api/v1/devices/{dev}/tags", headers=other_auth_headers)
    assert mine.json() == {}                       # tags are personal
    assert theirs.json() == {r"C:\f\a.pdf": ["to-read"]}
    # …but only for paths under their shared root
    r = await client.put(f"/api/v1/devices/{dev}/tags", headers=other_auth_headers,
                         json={"path": r"C:\other\b.txt", "tag": "x"})
    assert r.status_code == 404


async def test_tag_validation(client, auth_headers):
    dev = await _device(client, auth_headers)
    r = await client.put(f"/api/v1/devices/{dev}/tags", headers=auth_headers,
                         json={"path": "x", "tag": "bad;tage"} )
    assert r.status_code == 422


async def test_tag_on_foreign_device_denied(client, auth_headers, other_auth_headers):
    dev = await _device(client, other_auth_headers)
    r = await client.put(f"/api/v1/devices/{dev}/tags", headers=auth_headers,
                         json={"path": r"C:\x", "tag": "urgent"})
    assert r.status_code == 404


async def test_preferences_roundtrip_and_defaults(client, auth_headers):
    r = await client.get("/api/v1/me/preferences", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["discoverable"] is True
    assert r.json()["email"]
    r = await client.put("/api/v1/me/preferences", headers=auth_headers,
                         json={"display_name": "Henry", "discoverable": False})
    assert r.json()["discoverable"] is False
    r = await client.get("/api/v1/me/preferences", headers=auth_headers)
    assert r.json()["display_name"] == "Henry"


async def test_search_all_offline_devices_only(client, auth_headers):
    await _device(client, auth_headers)
    r = await client.get("/api/v1/files/search-all",
                         params={"q": "report"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["devices"][0]["status"] == "offline"


async def test_search_all_requires_query(client, auth_headers):
    r = await client.get("/api/v1/files/search-all", headers=auth_headers)
    assert r.status_code == 422
