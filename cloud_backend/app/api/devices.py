"""Device registry endpoints.

All routes require a valid Supabase JWT. Every operation is scoped to the
authenticated owner — one user can never see or mutate another's devices.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import current_auth, get_device_store
from app.errors import http_404
from app.schemas.devices import (
    DeviceRegisterRequest,
    DeviceResponse,
    DeviceStatusUpdate,
)
from app.security.jwt import AuthContext
from app.services.device_registry import DeviceNotFound, DeviceStore

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
) -> list[DeviceResponse]:
    return await store.list_devices(auth.user_id)


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    req: DeviceRegisterRequest,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
) -> DeviceResponse:
    return await store.register(auth.user_id, req)


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
) -> DeviceResponse:
    try:
        return await store.get_device(auth.user_id, device_id)
    except DeviceNotFound:
        raise http_404("device not found")


@router.patch("/{device_id}/status", response_model=DeviceResponse)
async def update_device_status(
    device_id: str,
    req: DeviceStatusUpdate,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
) -> DeviceResponse:
    try:
        return await store.set_status(auth.user_id, device_id, req.status)
    except DeviceNotFound:
        raise http_404("device not found")


@router.post("/{device_id}/revoke", response_model=DeviceResponse)
async def revoke_device(
    device_id: str,
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
) -> DeviceResponse:
    try:
        return await store.revoke(auth.user_id, device_id)
    except DeviceNotFound:
        raise http_404("device not found")
