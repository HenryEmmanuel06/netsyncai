"""Test fixtures: in-memory store + HS256 test tokens (no external services)."""

from __future__ import annotations

import time
import uuid

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

TEST_SECRET = "test-jwt-secret-not-for-production"
TEST_USER = "11111111-1111-1111-1111-111111111111"
OTHER_USER = "22222222-2222-2222-2222-222222222222"


def make_token(
    user_id: str = TEST_USER,
    secret: str = TEST_SECRET,
    exp_delta: int = 3600,
    aud: str = "authenticated",
) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": user_id,
            "aud": aud,
            "iat": now,
            "exp": now + exp_delta,
            "email": f"{user_id[:8]}@example.com",
            "role": "authenticated",
            "jti": str(uuid.uuid4()),
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "device_store", "memory")


@pytest.fixture(autouse=True)
def _clean_store():
    """The in-memory store is a process singleton — reset between tests."""
    from app.api import deps

    store = deps._memory_store
    for attr in ("_devices", "_sessions", "_pairing", "_credentials",
                 "_sync", "_shares", "_grants"):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {make_token()}"}


@pytest.fixture
def other_auth_headers():
    return {"Authorization": f"Bearer {make_token(OTHER_USER)}"}


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
