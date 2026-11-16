"""FastAPI dependency injection: auth + service wiring."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.security.jwt import AuthContext, AuthError, verify_token
from app.services.device_registry import DeviceStore, InMemoryDeviceStore
from app.services.supabase_store import SupabaseDeviceStore
from app.errors import http_401

bearer = HTTPBearer(auto_error=False)

# Single process-wide store for the memory backend so state survives requests.
_memory_store = InMemoryDeviceStore()
_supabase_store: SupabaseDeviceStore | None = None


def get_device_store() -> DeviceStore:
    if settings.device_store == "supabase":
        # reuse one instance (and its HTTP client + ensured-profile cache)
        global _supabase_store
        if _supabase_store is None:
            _supabase_store = SupabaseDeviceStore()
        return _supabase_store
    return _memory_store


async def current_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    store: DeviceStore = Depends(get_device_store),
) -> AuthContext:
    if creds is None:
        raise http_401("missing Authorization bearer token")
    try:
        auth = verify_token(creds.credentials)
    except AuthError as exc:
        raise http_401(str(exc)) from exc
    # self-heal: users who signed up before migrations/trigger lack a
    # profiles row, which 409s every FK'd write (pairing, devices, tags…)
    await store.ensure_profile(auth.user_id, auth.email)
    return auth


def request_id(request: Request) -> str:
    return request.headers.get("x-request-id", "-")
