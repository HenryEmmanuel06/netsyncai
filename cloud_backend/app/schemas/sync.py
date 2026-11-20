"""Sync session schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SyncCreateRequest(BaseModel):
    a_device_id: str
    a_path: str = Field(min_length=1)
    # Option 1 — sync onto a specific device/root (own device, or a shared
    # folder where the caller holds sync rights):
    b_device_id: str | None = None
    b_path: str | None = None
    # Option 2 — address the request to a colleague by email/handle/id; they
    # pick their destination folder when they accept:
    b_user: str | None = None
    mode: Literal["live", "review"] = "live"


class SyncAcceptRequest(BaseModel):
    """The accepting user's side of a pending sync request."""

    device_id: str
    root_path: str | None = None
    # single-folder sync: drop the shared folder into Downloads\<name>
    # on this device — the agent creates and registers it as readwrite.
    to_downloads: bool = False


class SyncParticipant(BaseModel):
    device_id: str
    root: str
    device_name: str = ""


class SyncSessionResponse(BaseModel):
    id: str
    name: str
    mode: str
    state: str
    created_by: str
    pending_user_id: str | None = None
    participants: list[SyncParticipant]
