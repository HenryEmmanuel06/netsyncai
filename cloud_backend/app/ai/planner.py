"""AI task planner: natural language → validated step plan → dispatch.

The LLM produces a JSON plan matching a response_schema; every step is
then re-validated here (allowlisted tools + per-tool arg schemas) BEFORE
anything reaches an agent. The model never executes commands — it only
proposes them, and sensitive ops require an explicit confirm flag.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.protocol import TOOL_NAMES

log = logging.getLogger("netsync.ai")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

# ops that touch data — require the caller to confirm the plan first
DESTRUCTIVE_TOOLS = {
    "delete_file", "rename_file", "move_file", "send_file",
    "stop_sync", "pause_sync",
}

TOOL_ARG_SCHEMAS: dict[str, dict[str, Any]] = {
    "browse_folder": {"path": str},
    "search_files": {"query": str, "ext": str, "limit": int},
    "download_file": {"path": str},
    "rename_file": {"path": str, "new_name": str},
    "move_file": {"src": str, "dst": str},
    "copy_file": {"src": str, "dst": str},
    "delete_file": {"path": str},
    "create_folder": {"path": str},
    "start_sync": {"session_id": str, "root": str, "peer_device_id": str},
    "pause_sync": {"session_id": str},
    "resume_sync": {"session_id": str},
    "stop_sync": {"session_id": str},
    "get_device_status": {},
    "get_transfer_status": {},
}
REQUIRED_ARGS: dict[str, set] = {
    "browse_folder": set(),
    "search_files": {"query"},
    "download_file": {"path"},
    "rename_file": {"path", "new_name"},
    "move_file": {"src", "dst"},
    "copy_file": {"src", "dst"},
    "delete_file": {"path"},
    "create_folder": {"path"},
    "start_sync": {"session_id", "root", "peer_device_id"},
    "pause_sync": {"session_id"},
    "resume_sync": {"session_id"},
    "stop_sync": {"session_id"},
}

PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "device": {"type": "STRING"},
                    "tool": {"type": "STRING"},
                    "args": {"type": "OBJECT"},
                    "description": {"type": "STRING"},
                },
                "required": ["tool"],
            },
        },
        "summary": {"type": "STRING"},
    },
    "required": ["steps"],
}

SYSTEM_PROMPT = """You are the planner for NetSync AI, a distributed file system.
Convert the user's request into a JSON plan of tool calls.

Available tools and required args:
- browse_folder {path} — list a directory on a device
- search_files {query, ext?, limit?} — search the device's file index
- download_file {path} — fetch a file
- rename_file {path, new_name}
- move_file {src, dst}
- copy_file {src, dst}
- delete_file {path}
- create_folder {path}
- start_sync {session_id, root, peer_device_id}
- pause_sync / resume_sync / stop_sync {session_id}
- get_device_status {} — sync/session status on a device

Rules:
- "device" is the target device NAME; it will be resolved to an id.
- If the request is ambiguous, produce a single get_device_status or
  browse_folder step to gather info rather than guessing destructive ops.
- Never invent absolute paths the user didn't give; prefer search_files
  first when the exact path is unknown.
- Output ONLY the JSON plan."""


class PlanStep(BaseModel):
    device: str | None = None
    tool: str
    args: dict[str, Any] = {}
    description: str | None = None


class Plan(BaseModel):
    steps: list[PlanStep]
    summary: str | None = None


class PlanError(Exception):
    pass


async def generate_plan(prompt: str, device_names: list[str]) -> Plan:
    """Call Gemini; returns a validated Plan or raises PlanError."""
    if not settings.gemini_api_key:
        raise PlanError("GEMINI_API_KEY not configured on the backend")

    url = GEMINI_URL.format(
        model=settings.gemini_model, key=settings.gemini_api_key
    )
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": (
            f"User devices: {', '.join(device_names) or 'none'}\n\n"
            f"Request: {prompt}"
        )}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": PLAN_SCHEMA,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise PlanError(f"gemini request failed: {exc}") from exc

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        plan = Plan.model_validate_json(text)
    except (KeyError, IndexError, ValidationError, ValueError) as exc:
        raise PlanError(f"invalid plan from model: {exc}") from exc

    validate_steps(plan.steps)
    return plan


def validate_steps(steps: list[PlanStep]) -> None:
    """Re-validate every step — the LLM output is untrusted input."""
    for i, s in enumerate(steps):
        # the planner may only use tools with an explicit arg schema —
        # folder sharing/management is never AI-controllable
        if s.tool not in TOOL_NAMES or s.tool not in TOOL_ARG_SCHEMAS:
            raise PlanError(f"step {i}: unknown tool '{s.tool}'")
        allowed = TOOL_ARG_SCHEMAS.get(s.tool, {})
        required = REQUIRED_ARGS.get(s.tool, set())
        for arg in s.args:
            if arg not in allowed:
                raise PlanError(f"step {i}: '{s.tool}' has no arg '{arg}'")
        missing = required - s.args.keys()
        if missing:
            raise PlanError(f"step {i}: '{s.tool}' missing {missing}")
        for arg, val in s.args.items():
            want = allowed[arg]
            if want is str and not isinstance(val, str):
                raise PlanError(f"step {i}: '{s.tool}.{arg}' must be a string")
            if want is int and not isinstance(val, int):
                raise PlanError(f"step {i}: '{s.tool}.{arg}' must be an int")


def needs_confirmation(plan: Plan) -> bool:
    return any(s.tool in DESTRUCTIVE_TOOLS for s in plan.steps)
