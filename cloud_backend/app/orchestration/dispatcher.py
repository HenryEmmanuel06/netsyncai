"""Command dispatcher: REST → command.dispatch → command.result.

Correlates responses by step_id. Phase 5's task engine will queue and
compose these; for now each API call is a single dispatch.
"""

from __future__ import annotations

import asyncio
import uuid

from app.networking.connections import manager
from app.protocol import CommandDispatch, Envelope, MessageType, TOOL_NAMES


class DeviceOffline(Exception):
    pass


class CommandFailed(Exception):
    def __init__(self, error: str):
        super().__init__(error)
        self.error = error


class CommandTimeout(Exception):
    pass


_pending: dict[str, asyncio.Future] = {}
DISPATCH_TIMEOUT = 30.0


async def send_command(device_id: str, tool: str, args: dict) -> str:
    """Put a tool command on the agent's socket; returns the step_id to
    later await_result() on. Used when the caller must interleave other
    messages (e.g. transfer chunks) before the result arrives."""
    if tool not in TOOL_NAMES:
        raise CommandFailed(f"unknown tool: {tool}")
    if not manager.is_connected(device_id):
        raise DeviceOffline(device_id)

    step_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    _pending[step_id] = loop.create_future()
    env = Envelope(
        type=MessageType.COMMAND_DISPATCH,
        payload=CommandDispatch(
            task_id="rest", step_id=step_id, tool=tool, args=args,
        ).model_dump(),
    )
    await manager.send(device_id, env.model_dump_json())
    return step_id


async def await_result(step_id: str, timeout: float = DISPATCH_TIMEOUT) -> dict:
    fut = _pending.get(step_id)
    if fut is None:
        raise CommandFailed("unknown step_id")
    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
    finally:
        _pending.pop(step_id, None)
    if not result.get("ok"):
        raise CommandFailed(result.get("error", "command failed"))
    return result.get("result", {})


async def dispatch(device_id: str, tool: str, args: dict, timeout: float = DISPATCH_TIMEOUT) -> dict:
    """Send a tool command to a connected agent; await its result."""
    step_id = await send_command(device_id, tool, args)
    return await await_result(step_id, timeout)


def resolve(step_id: str, result: dict) -> None:
    """Called by the WS handler when a command.result arrives."""
    fut = _pending.get(step_id)
    if fut and not fut.done():
        fut.set_result(result)


def pending_count() -> int:
    return len(_pending)
