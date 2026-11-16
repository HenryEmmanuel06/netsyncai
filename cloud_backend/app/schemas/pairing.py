"""Pairing request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PairingCreateRequest(BaseModel):
    device_name: str = Field(min_length=1, max_length=80)


class PairingCreateResponse(BaseModel):
    code: str           # shown once to the owner; never stored raw
    expires_at: datetime
    expires_in_seconds: int


class PairingRedeemRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    agent_version: str | None = Field(default=None, max_length=32)


class PairingRedeemResponse(BaseModel):
    device_id: str
    device_name: str
    device_credential: str   # shown once; agent stores it locally
