"""Activity feed for the signed-in user (backed by activity_logs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import current_auth, get_device_store
from app.security.jwt import AuthContext
from app.services.device_registry import DeviceStore

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def list_activity(
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(current_auth),
    store: DeviceStore = Depends(get_device_store),
):
    return await store.list_activity(auth.user_id, limit)
