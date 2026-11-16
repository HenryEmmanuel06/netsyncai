"""Colleague sync: a session may span two accounts via a start_sync grant."""

import pytest

from tests.conftest import OTHER_USER

pytestmark = pytest.mark.asyncio

ROOT_MINE = r"C:\my\sync"
ROOT_THEIRS = r"C:\their\shared"


async def _setup(client, auth_headers, other_auth_headers, bits):
    mine = (await client.post("/api/v1/devices", json={"name": "Mine"},
                              headers=auth_headers)).json()["id"]
    theirs = (await client.post("/api/v1/devices", json={"name": "Colleague-PC"},
                                headers=other_auth_headers)).json()["id"]
    share = (await client.post("/api/v1/sharing", headers=other_auth_headers,
                               json={"device_id": theirs, "root_path": ROOT_THEIRS})
             ).json()
    await client.post(f"/api/v1/sharing/{share['id']}/grants",
                      headers=other_auth_headers,
                      json={"subject": _test_user(), "permissions": bits})
    return mine, theirs


def _test_user():
    from tests.conftest import TEST_USER
    return TEST_USER


async def test_sync_to_colleague_requires_start_sync_bit(
    client, auth_headers, other_auth_headers
):
    mine, theirs = await _setup(client, auth_headers, other_auth_headers,
                                bits=1 + 2 + 4)  # no 256
    r = await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_device_id": theirs, "b_path": ROOT_THEIRS, "mode": "live",
    })
    assert r.status_code == 404


async def test_sync_to_colleague_path_outside_share_denied(
    client, auth_headers, other_auth_headers
):
    mine, theirs = await _setup(client, auth_headers, other_auth_headers, bits=256)
    r = await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_device_id": theirs, "b_path": r"C:\their\elsewhere", "mode": "live",
    })
    assert r.status_code == 404


async def test_cross_account_sync_created_and_visible_to_both(
    client, auth_headers, other_auth_headers
):
    mine, theirs = await _setup(client, auth_headers, other_auth_headers, bits=256 + 1)
    r = await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_device_id": theirs, "b_path": ROOT_THEIRS, "mode": "live",
    })
    assert r.status_code == 201
    sid = r.json()["id"]
    # offline agents → session lands in error state but exists
    assert r.json()["state"] in ("active", "error")

    # colleague sees it too (their device participates)
    theirs_sessions = (await client.get("/api/v1/sync",
                                        headers=other_auth_headers)).json()
    assert [s["id"] for s in theirs_sessions] == [sid]

    # colleague (device owner) can pause it
    r = await client.post(f"/api/v1/sync/{sid}/pause", headers=other_auth_headers)
    assert r.status_code == 200
    assert r.json()["state"] == "paused"


async def test_cross_account_sync_hidden_from_strangers(
    client, auth_headers, other_auth_headers
):
    mine, theirs = await _setup(client, auth_headers, other_auth_headers, bits=256)
    sid = (await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_device_id": theirs, "b_path": ROOT_THEIRS, "mode": "live",
    })).json()["id"]
    # a third user (OTHER_USER owns `theirs` here, so use a fresh outsider)
    r = await client.post(f"/api/v1/sync/{sid}/pause",
                          headers={"Authorization": "Bearer outsider-token"})
    assert r.status_code == 401
