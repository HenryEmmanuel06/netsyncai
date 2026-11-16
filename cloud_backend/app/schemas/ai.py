"""AI task endpoint schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    confirm: bool = False   # required when the plan contains destructive tools


class PlanStepOut(BaseModel):
    device: str | None
    tool: str
    args: dict[str, Any]
    description: str | None = None
    ok: bool | None = None
    result: Any = None
    error: str | None = None


class TaskResponse(BaseModel):
    summary: str | None
    needs_confirmation: bool
    executed: bool
    steps: list[PlanStepOut]
