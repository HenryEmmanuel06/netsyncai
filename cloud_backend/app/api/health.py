"""Health/readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.service_name}


@router.get("/ready")
async def ready() -> dict:
    # Later: check Postgres reachability. For now readiness = process up.
    return {"ready": True, "device_store": settings.device_store}
