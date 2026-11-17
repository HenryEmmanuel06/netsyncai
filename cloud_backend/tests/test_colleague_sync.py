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
    # cross-account sessions start as pending requests — the colleague must
    # accept before any agent starts syncing
    assert r.json()["state"] == "pending"

    # colleague sees it in their session list AND their request inbox
    theirs_sessions = (await client.get("/api/v1/sync",
                                        headers=other_auth_headers)).json()
    assert [s["id"] for s in theirs_sessions] == [sid]
    req = (await client.get("/api/v1/sync/requests",
                            headers=other_auth_headers)).json()["requests"]
    assert [q["id"] for q in req] == [sid]
    # requester does NOT see their own request as incoming
    mine_req = (await client.get("/api/v1/sync/requests",
                                 headers=auth_headers)).json()["requests"]
    assert mine_req == []

    # the colleague accepts — agents are offline so it lands in error state
    r = await client.post(f"/api/v1/sync/{sid}/accept", headers=other_auth_headers)
    assert r.json()["state"] in ("active", "error")
    # inbox clears once resolved
    req = (await client.get("/api/v1/sync/requests",
                            headers=other_auth_headers)).json()["requests"]
    assert req == []

    # colleague (device owner) can pause it
    r = await client.post(f"/api/v1/sync/{sid}/pause", headers=other_auth_headers)
    assert r.status_code == 200
    assert r.json()["state"] == "paused"


async def test_cross_account_sync_decline(
    client, auth_headers, other_auth_headers
):
    mine, theirs = await _setup(client, auth_headers, other_auth_headers, bits=256 + 1)
    sid = (await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_device_id": theirs, "b_path": ROOT_THEIRS, "mode": "live",
    })).json()["id"]
    r = await client.post(f"/api/v1/sync/{sid}/decline", headers=other_auth_headers)
    assert r.status_code == 200
    assert r.json()["state"] == "stopped"
    req = (await client.get("/api/v1/sync/requests",
                            headers=other_auth_headers)).json()["requests"]
    assert req == []


async def test_sync_request_addressed_by_user_id(
    client, auth_headers, other_auth_headers
):
    """A requester who knows only the colleague's identity (not their
    devices) can send a sync request; the recipient picks the destination
    folder on accept and the content downloads to their PC."""
    mine = (await client.post("/api/v1/devices", json={"name": "Mine"},
                              headers=auth_headers)).json()["id"]
    theirs = (await client.post("/api/v1/devices", json={"name": "Colleague-PC"},
                                headers=other_auth_headers)).json()["id"]

    r = await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_user": OTHER_USER, "mode": "live",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["state"] == "pending"
    assert r.json()["pending_user_id"] == OTHER_USER
    assert len(r.json()["participants"]) == 1

    # recipient sees it as a needs-folder request AND in their session list
    req = (await client.get("/api/v1/sync/requests",
                            headers=other_auth_headers)).json()["requests"]
    assert [q["id"] for q in req] == [sid]
    assert req[0]["needs_folder"] is True
    theirs_sessions = (await client.get("/api/v1/sync",
                                        headers=other_auth_headers)).json()
    assert [s["id"] for s in theirs_sessions] == [sid]

    # accepting without choosing a destination is rejected
    r = await client.post(f"/api/v1/sync/{sid}/accept",
                          headers=other_auth_headers)
    assert r.status_code == 422

    # the requester cannot accept on the recipient's behalf
    r = await client.post(f"/api/v1/sync/{sid}/accept",
                          headers=auth_headers,
                          json={"device_id": mine, "root_path": ROOT_MINE})
    assert r.status_code == 404

    # accepting with a destination joins the session and activates it
    r = await client.post(f"/api/v1/sync/{sid}/accept",
                          headers=other_auth_headers,
                          json={"device_id": theirs, "root_path": ROOT_THEIRS})
    assert r.status_code == 200
    assert r.json()["state"] in ("active", "error")
    assert {p["device_id"] for p in r.json()["participants"]} == {mine, theirs}
    assert r.json()["pending_user_id"] is None


async def test_sync_request_unknown_user(client, auth_headers):
    mine = (await client.post("/api/v1/devices", json={"name": "Mine"},
                              headers=auth_headers)).json()["id"]
    r = await client.post("/api/v1/sync", headers=auth_headers, json={
        "a_device_id": mine, "a_path": ROOT_MINE,
        "b_user": "nobody@example.com", "mode": "live",
    })
    assert r.status_code == 422


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
