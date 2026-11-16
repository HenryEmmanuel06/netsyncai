"""Request/response schemas for the device registry API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DeviceStatusLiteral = Literal["online", "busy", "invisible", "offline"]


class DeviceRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    platform: str = Field(default="windows", max_length=32)
    agent_version: str | None = Field(default=None, max_length=32)


class DeviceResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    platform: str
    agent_version: str | None = None
    status: DeviceStatusLiteral = "offline"
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class DeviceStatusUpdate(BaseModel):
    status: DeviceStatusLiteral
