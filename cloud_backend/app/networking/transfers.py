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
CHUNK_SIZE = 64 * 1024


def register(transfer_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=64)  # backpressure
    _queues[transfer_id] = q
    return q


def unregister(transfer_id: str) -> None:
    _queues.pop(transfer_id, None)


async def route(env: Envelope) -> None:
    """ws_agent feeds every TRANSFER_* envelope here."""
    payload = env.payload
    tid = payload.get("transfer_id")
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
