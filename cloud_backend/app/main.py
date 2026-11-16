"""NetSync AI cloud coordination backend.

Phase 1: health, Supabase JWT auth, device registry.
Phase 2 adds: pairing, agent WebSocket (/ws/agent), presence.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, devices, files, health, pairing, sync, ws_agent
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(devices.router, prefix="/api/v1")
app.include_router(pairing.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(ws_agent.router)
