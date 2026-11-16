"""Transfer relay: TRANSFER_* envelopes ↔ asyncio queues.

For Phase 3, file payloads travel over the agent's existing WSS as base64
chunks (the "relay" transport — works behind any NAT). The download/upload
REST endpoints consume a queue; direct LAN P2P lands behind the same
interface later.
"""

from __future__ import annotations

import asyncio
import base64

from app.protocol import (
    Envelope,
    MessageType,
    TransferBegin,
    TransferChunk,
    TransferEnd,
)

_queues: dict[str, asyncio.Queue] = {}
_routes: dict[str, str] = {}   # transfer_id -> dest device_id (agent→agent)
CHUNK_SIZE = 64 * 1024


def register(transfer_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=64)  # backpressure
    _queues[transfer_id] = q
    return q


def unregister(transfer_id: str) -> None:
    _queues.pop(transfer_id, None)


async def route(env: Envelope, raw: str | None = None) -> None:
    """ws_agent feeds every TRANSFER_* envelope here.

    If TRANSFER_BEGIN.meta.dest_device names a device, this transfer is
    agent→agent (sync): chunks get forwarded to that device's socket.
    Otherwise they land in the REST-facing queue for downloads/uploads.
    """
    from app.networking.connections import manager

    payload = env.payload
    tid = payload.get("transfer_id")
    if env.type is MessageType.TRANSFER_BEGIN:
        dest = payload.get("meta", {}).get("dest_device")
        if dest:
            _routes[tid] = dest
            await manager.send(dest, raw or env.model_dump_json())
            return
    dest = _routes.get(tid)
    if dest:
        await manager.send(dest, raw or env.model_dump_json())
        if env.type in (MessageType.TRANSFER_END, MessageType.TRANSFER_ABORT):
            _routes.pop(tid, None)
        return
    q = _queues.get(tid)
    if q is not None:
        await q.put(env)


def chunk_envelope(transfer_id: str, seq: int, data: bytes) -> Envelope:
    return Envelope(
        type=MessageType.TRANSFER_CHUNK,
        payload=TransferChunk(
            transfer_id=transfer_id, seq=seq, data=base64.b64encode(data).decode()
        ).model_dump(),
    )


def decode_chunk(env: Envelope) -> bytes:
    return base64.b64decode(env.payload["data"])


__all__ = [
    "register", "unregister", "route", "chunk_envelope", "decode_chunk",
    "TransferBegin", "TransferEnd", "CHUNK_SIZE",
]
