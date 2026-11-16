"""Access requests + user blocking + device stats endpoints."""

import pytest

from app.api import deps
from tests.conftest import OTHER_USER, TEST_USER

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


async def test_access_request_flow(client, auth_headers, other_auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/request",
                          headers=other_auth_headers, json={"role": "editor"})
    assert r.status_code == 201

    r = await client.get("/api/v1/sharing/requests", headers=auth_headers)
    assert r.json()["incoming"][0]["requester_id"] == OTHER_USER
    assert r.json()["incoming"][0]["status"] == "pending"
    r2 = await client.get("/api/v1/sharing/requests", headers=other_auth_headers)
    assert r2.json()["outgoing"][0]["status"] == "pending"

    req_id = r.json()["incoming"][0]["id"]
    r = await client.post(f"/api/v1/sharing/requests/{req_id}/approve",
                          headers=auth_headers, json={"role": "editor"})
    assert r.status_code == 200
    r = await client.get(f"/api/v1/sharing/{folder_id}/grants", headers=auth_headers)
    assert any(g["subject_user_id"] == OTHER_USER for g in r.json())


async def test_request_rejected_on_own_folder(client, auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    r = await client.post(f"/api/v1/sharing/{folder_id}/request",
                          headers=auth_headers, json={"role": "viewer"})
    assert r.status_code == 422


async def test_only_owner_resolves(client, auth_headers, other_auth_headers):
    _, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/request",
                      headers=other_auth_headers, json={"role": "viewer"})
    reqs = await client.get("/api/v1/sharing/requests", headers=auth_headers)
    req_id = reqs.json()["incoming"][0]["id"]
    r = await client.post(f"/api/v1/sharing/requests/{req_id}/approve",
                          headers=other_auth_headers, json={"role": "viewer"})
    assert r.status_code == 422


async def test_block_overrides_grant(client, auth_headers, other_auth_headers):
    dev_id, folder_id = await _setup_share(client, auth_headers)
    await client.post(f"/api/v1/sharing/{folder_id}/grants", headers=auth_headers,
                      json={"subject": OTHER_USER, "permissions": 2047})
    store = deps._memory_store
    assert await store.effective_permissions(OTHER_USER, dev_id, ROOT) == 2047

    r = await client.post("/api/v1/sharing/blocks", headers=auth_headers,
                          json={"subject": OTHER_USER})
    assert r.status_code == 201
    assert await store.effective_permissions(OTHER_USER, dev_id, ROOT) == 0

    r = await client.get("/api/v1/sharing/blocks", headers=auth_headers)
    assert r.json()["blocked"][0]["user_id"] == OTHER_USER

    r = await client.delete(f"/api/v1/sharing/blocks/{OTHER_USER}",
                            headers=auth_headers)
    assert r.status_code == 204
    assert await store.effective_permissions(OTHER_USER, dev_id, ROOT) == 2047


async def test_block_cannot_self(client, auth_headers):
    r = await client.post("/api/v1/sharing/blocks", headers=auth_headers,
                          json={"subject": TEST_USER})
    assert r.status_code == 422
