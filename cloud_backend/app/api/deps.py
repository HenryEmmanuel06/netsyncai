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


def get_device_store() -> DeviceStore:
    if settings.device_store == "supabase":
        return SupabaseDeviceStore()
    return _memory_store


async def current_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthContext:
    if creds is None:
        raise http_401("missing Authorization bearer token")
    try:
        return verify_token(creds.credentials)
    except AuthError as exc:
        raise http_401(str(exc)) from exc


def request_id(request: Request) -> str:
    return request.headers.get("x-request-id", "-")
