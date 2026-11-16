"""Sync session schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SyncCreateRequest(BaseModel):
    a_device_id: str
    a_path: str = Field(min_length=1)
    b_device_id: str
    b_path: str = Field(min_length=1)
    mode: Literal["live", "review"] = "live"


class SyncParticipant(BaseModel):
    device_id: str
    root: str


class SyncSessionResponse(BaseModel):
    id: str
    name: str
    mode: str
    state: str
    created_by: str
    participants: list[SyncParticipant]
