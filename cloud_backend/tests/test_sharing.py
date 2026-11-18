"""Cross-user sharing tests — grants, resolution, enforcement bits."""

import pytest

from tests.conftest import OTHER_USER, TEST_USER, make_token as _token

pytestmark = pytest.mark.asyncio

ROOT = r"C:\shared\docs"


async def _setup_share(client, auth_headers):
    """Owner registers device + share; returns (device_id, folder_id)."""
    r = await client.post("/api/v1/devices", json={"name": "PC"},
                          headers=auth_headers)
    dev = r.json()
    r = await client.post("/api/v1/sharing", headers=auth_headers, json={
        "device_id": dev["id"], "root_path": ROOT, "label": "Docs",
    })
    return dev["id"], r.json()["id"]


async def test_create_and_list_share(client, auth_headers):
    dev_id, folder_id = await _setup_share(client, auth_headers)
    r = await client.get("/api/v1/sharing", headers=auth_headers)
    assert r.status_code == 200
    owned = r.json()["owned"]
    assert owned[0]["root_path"] == ROOT
    assert owned[0]["device_id"] == dev_id


async def test_share_requires_device_ownership(client, auth_headers):
    r = await client.post("/api/v1/sharing", headers=auth_headers, json={
        "device_id": "not-mine", "root_path": ROOT,
    })
    assert r.status_code == 404


async def test_grant_and_resolve(client, auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": OTHER_USER, "permissions": 3})
    assert r.status_code == 201
    assert r.json()["permissions_granted"] == 3

    # grantee sees it in their "granted" list
    r = await client.get("/api/v1/sharing", headers={
        "Authorization": f"Bearer {_other_token()}"
    })
    granted = r.json()["granted"]
    assert len(granted) == 1
    assert granted[0]["permissions"] == 3


async def test_grant_by_email_or_handle_unresolvable_in_memory(
    client, auth_headers
):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": "not-a-uuid", "permissions": 1})
    assert r.status_code == 422


async def test_grant_self_denied(client, auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": TEST_USER, "permissions": 1})
    assert r.status_code == 422


async def test_grant_by_non_owner_denied(client, auth_headers, other_auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=other_auth_headers,
                          json={"subject": TEST_USER, "permissions": 1})
    assert r.status_code == 403


async def test_revoke_grant(client, auth_headers, other_auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": OTHER_USER, "permissions": 1})
    grant_id = r.json()["id"]
    r = await client.delete(
        f"/api/v1/sharing/{folder_id}/grants/{grant_id}",
        headers=auth_headers,
    )
    assert r.status_code == 204
    r = await client.get("/api/v1/sharing", headers=other_auth_headers)
    assert r.json()["granted"] == []


async def test_revoked_device_takes_its_shares(client, auth_headers,
                                               other_auth_headers):
    """A removed device takes its shares with it — the grantee's 'shared with
    me' list must not keep showing folders that can never be reached."""
    dev_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 1})
    r = await client.get("/api/v1/sharing", headers=other_auth_headers)
    assert len(r.json()["granted"]) == 1

    r = await client.post(f"/api/v1/devices/{dev_id}/revoke",
                          headers=auth_headers)
    assert r.status_code == 200

    r = await client.get("/api/v1/sharing", headers=other_auth_headers)
    assert r.json()["granted"] == []
    r = await client.get("/api/v1/sharing", headers=auth_headers)
    assert r.json()["owned"] == []


async def test_manager_can_delegate_grants(client, auth_headers,
                                           other_auth_headers):
    """A collaborator with Manager bits can grant others access to the
    owner's share — capped at Editor, and the share stays the owner's."""
    THIRD = "33333333-3333-3333-3333-333333333333"
    dev_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 2047})

    # manager grants uche an editor grant on the owner's share
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=other_auth_headers,
                          json={"subject": THIRD, "permissions": 255})
    assert r.status_code == 201

    # …but cannot escalate another manager
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=other_auth_headers,
                          json={"subject": THIRD, "permissions": 2047})
    assert r.status_code == 403

    # managers can list grants on the share too
    r = await client.get(f"/api/v1/sharing/{folder_id}/grants",
                         headers=other_auth_headers)
    assert r.status_code == 200

    # uche sees the folder — under the owner's share, not the manager's
    third_headers = {"Authorization": f"Bearer {_token(THIRD)}"}
    r = await client.get("/api/v1/sharing", headers=third_headers)
    granted = r.json()["granted"]
    assert len(granted) == 1
    assert granted[0]["device_id"] == dev_id
    assert granted[0]["owner_id"] == TEST_USER


async def test_file_access_denied_without_grant(
    client, auth_headers, other_auth_headers
):
    dev_id, _ = await _setup_share(client, auth_headers)
    # other user tries to browse the shared device — no grant yet
    r = await client.get(
        f"/api/v1/devices/{dev_id}/browse",
        params={"path": ROOT}, headers=other_auth_headers,
    )
    assert r.status_code == 404  # device existence not leaked


async def test_file_access_with_grant_offline(
    client, auth_headers, other_auth_headers
):
    """Grantee has browse permission — device is offline so the dispatch
    fails, but permission resolution happened (409 not 404)."""
    dev_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 1})
    r = await client.get(
        f"/api/v1/devices/{dev_id}/browse",
        params={"path": ROOT}, headers=other_auth_headers,
    )
    assert r.status_code == 409  # passed authz → device offline


async def test_write_bit_required(client, auth_headers, other_auth_headers):
    """Grantee with only browse (1) cannot rename (needs bit 8)."""
    dev_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 1})
    r = await client.post(
        f"/api/v1/devices/{dev_id}/rename",
        json={"path": f"{ROOT}\\f.txt", "new_name": "g.txt"},
        headers=other_auth_headers,
    )
    assert r.status_code == 404  # rename bit missing → denied before dispatch


async def test_path_outside_root_denied(client, auth_headers, other_auth_headers):
    dev_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 255})
    r = await client.post(
        f"/api/v1/devices/{dev_id}/rename",
        json={"path": r"C:\other\secret.txt", "new_name": "x"},
        headers=other_auth_headers,
    )
    assert r.status_code == 404  # outside granted root


def _other_token():
    from tests.conftest import OTHER_USER, make_token
    return make_token(OTHER_USER)
