"""NetSync AI cloud coordination backend.

Phase 1: health, Supabase JWT auth, device registry.
Phase 2 adds: pairing, agent WebSocket (/ws/agent), presence.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api import devices, health
from app.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="NetSync AI Coordinator",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
)

app.include_router(health.router)
app.include_router(devices.router, prefix="/api/v1")
