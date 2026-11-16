"""Sharing & permission schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    device_id: str
    root_path: str = Field(min_length=1)
    label: str = ""


class GrantRequest(BaseModel):
    subject: str = Field(min_length=1)   # uuid | email | @handle
    permissions: int = Field(ge=0, le=2047)


class SharedFolderResponse(BaseModel):
    id: str
    owner_id: str
    device_id: str
    device_name: str
    label: str
    root_path: str
    created_at: datetime | str | None = None
    permissions: int | None = None   # set on granted-list entries
    grant_id: str | None = None


class GrantResponse(BaseModel):
    id: str
    folder_id: str
    subject_user_id: str
    permissions_granted: int
    created_at: datetime | str | None = None


class SharesResponse(BaseModel):
    owned: list[SharedFolderResponse]
    granted: list[SharedFolderResponse]
