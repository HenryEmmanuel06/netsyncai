"""Editor/Manager grants are rejected while the on-device root is read-only."""

import pytest

from app.orchestration.dispatcher import DeviceOffline
from tests.conftest import OTHER_USER

pytestmark = pytest.mark.asyncio

ROOT = r"C:\shared\docs"


async def _setup_share(client, auth_headers):
    r = await client.post("/api/v1/devices", json={"name": "PC"},
                          headers=auth_headers)
    dev = r.json()
    r = await client.post("/api/v1/sharing", headers=auth_headers, json={
        "device_id": dev["id"], "root_path": ROOT, "label": "Docs",
    })
    return dev["id"], r.json()["id"]


def _agent_folders(access: str):
    async def fake_dispatch(device_id, tool, args, timeout=None):
        assert tool == "list_folders"
        return {"folders": [{"path": ROOT, "label": "Docs", "access": access}]}
    return fake_dispatch


async def test_editor_rejected_on_read_only_root(client, auth_headers, monkeypatch):
    _, folder_id = await _setup_share(client, auth_headers)
    monkeypatch.setattr("app.api.sharing.dispatch", _agent_folders("read"))

    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": OTHER_USER, "permissions": 255})
    assert r.status_code == 409
    assert "read-only" in r.json()["detail"]["error"].lower()

    # viewer is still fine on a read-only root
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": OTHER_USER, "permissions": 3})
    assert r.status_code == 201


async def test_editor_allowed_on_readwrite_root(client, auth_headers, monkeypatch):
    _, folder_id = await _setup_share(client, auth_headers)
    monkeypatch.setattr("app.api.sharing.dispatch", _agent_folders("readwrite"))

    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": OTHER_USER, "permissions": 255})
    assert r.status_code == 201


async def test_unverifiable_root_does_not_block(client, auth_headers, monkeypatch):
    """Agent offline → grant proceeds; the agent enforces its flags at op time."""
    _, folder_id = await _setup_share(client, auth_headers)

    async def offline(device_id, tool, args, timeout=None):
        raise DeviceOffline(device_id)

    monkeypatch.setattr("app.api.sharing.dispatch", offline)
    r = await client.post(f"/api/v1/sharing/{folder_id}/grants",
                          headers=auth_headers,
                          json={"subject": OTHER_USER, "permissions": 2047})
    assert r.status_code == 201


async def test_approve_request_enforced(client, auth_headers,
                                        other_auth_headers, monkeypatch):
    _, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/request",
                      headers=other_auth_headers, json={"role": "editor"})
    reqs = await client.get("/api/v1/sharing/requests", headers=auth_headers)
    req_id = reqs.json()["incoming"][0]["id"]

    monkeypatch.setattr("app.api.sharing.dispatch", _agent_folders("read"))
    r = await client.post(f"/api/v1/sharing/requests/{req_id}/approve",
                          headers=auth_headers, json={"role": "editor"})
    assert r.status_code == 409
    r = await client.post(f"/api/v1/sharing/requests/{req_id}/approve",
                          headers=auth_headers, json={"role": "viewer"})
    assert r.status_code == 200


async def test_removing_root_revokes_share_for_colleagues(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """Stop-sharing on the device deletes the share record + grants, so the
    folder disappears from the colleague's Shared-with-me list."""
    device_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 3})
    granted = (await client.get("/api/v1/sharing",
                                headers=other_auth_headers)).json()["granted"]
    assert len(granted) == 1

    async def fake_dispatch(device_id, tool, args, timeout=None):
        assert tool == "remove_folder"
        return {"removed": args["path"]}

    monkeypatch.setattr("app.api.folders.dispatch", fake_dispatch)
    r = await client.post(f"/api/v1/devices/{device_id}/folders/remove",
                          headers=auth_headers, json={"path": ROOT})
    assert r.status_code == 200

    # colleague no longer sees it; owner has no share record either
    granted = (await client.get("/api/v1/sharing",
                                headers=other_auth_headers)).json()["granted"]
    assert granted == []
    owned = (await client.get("/api/v1/sharing",
                              headers=auth_headers)).json()["owned"]
    assert owned == []


async def test_ghost_share_pruned_when_device_reachable(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """A share whose root the agent no longer reports disappears from the
    colleague's list — self-heals shares removed outside this API."""
    device_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 3})

    async def fake_dispatch(device_id, tool, args, timeout=None):
        assert tool == "list_folders"
        return {"folders": []}  # agent no longer shares ROOT

    monkeypatch.setattr("app.services.reconcile.dispatch", fake_dispatch)

    granted = (await client.get("/api/v1/sharing",
                                headers=other_auth_headers)).json()["granted"]
    assert granted == []
    # the record is deleted, not just hidden
    owned = (await client.get("/api/v1/sharing",
                              headers=auth_headers)).json()["owned"]
    assert owned == []


async def test_ghost_share_kept_when_device_offline(
    client, auth_headers, other_auth_headers, monkeypatch
):
    """Can't verify while the device is unreachable — don't prune."""
    _, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants",
                      headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 3})

    async def offline(device_id, tool, args, timeout=None):
        raise DeviceOffline(device_id)

    monkeypatch.setattr("app.services.reconcile.dispatch", offline)

    granted = (await client.get("/api/v1/sharing",
                                headers=other_auth_headers)).json()["granted"]
    assert len(granted) == 1
