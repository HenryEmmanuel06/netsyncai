import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


async def test_missing_token_rejected(client):
    r = await client.get("/api/v1/devices")
    assert r.status_code == 401


async def test_garbage_token_rejected(client):
    r = await client.get(
        "/api/v1/devices", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert r.status_code == 401


async def test_wrong_secret_rejected(client):
    token = make_token(secret="a-different-secret-that-is-long-enough")
    r = await client.get(
        "/api/v1/devices", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_expired_token_rejected(client):
    token = make_token(exp_delta=-10)
    r = await client.get(
        "/api/v1/devices", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_wrong_audience_rejected(client):
    token = make_token(aud="service_role")
    r = await client.get(
        "/api/v1/devices", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


async def test_valid_token_accepted(client, auth_headers):
    r = await client.get("/api/v1/devices", headers=auth_headers)
    assert r.status_code == 200
