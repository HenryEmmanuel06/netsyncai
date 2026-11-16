import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, headers):
    r = await client.post(
        "/api/v1/devices", json={"name": "File-PC"}, headers=headers
    )
    return r.json()


async def test_browse_offline_device(client, auth_headers):
    dev = await _register(client, auth_headers)
    r = await client.get(
        f"/api/v1/devices/{dev['id']}/browse", headers=auth_headers
    )
    assert r.status_code == 409
    assert "offline" in r.json()["detail"]["error"]


async def test_browse_other_users_device(client, other_auth_headers):
    r = await client.get(
        "/api/v1/devices/any-id/browse", headers=other_auth_headers
    )
    assert r.status_code == 404


async def test_files_endpoints_require_auth(client):
    for method, url in [
        ("get", "/api/v1/devices/x/browse"),
        ("get", "/api/v1/devices/x/search"),
        ("post", "/api/v1/devices/x/rename"),
        ("delete", "/api/v1/devices/x/file?path=a"),
    ]:
        r = await getattr(client, method)(url)
        assert r.status_code == 401


async def test_search_offline(client, auth_headers):
    dev = await _register(client, auth_headers)
    r = await client.get(
        f"/api/v1/devices/{dev['id']}/search?q=x", headers=auth_headers
    )
    assert r.status_code == 409
