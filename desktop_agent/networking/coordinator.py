"""Coordinator connectivity: pairing redeem + persistent WebSocket loop.

The agent initiates everything outbound (HTTPS for pairing, WSS for the
session) — nothing listens inbound, so it works behind NAT/firewall.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random

import httpx
import websockets

from protocol import AgentHello, DeviceStatus, Envelope, MessageType

log = logging.getLogger("netsync.coordinator")

HEARTBEAT_SECONDS = 30
HELLO_ACK_TIMEOUT = 10.0
BACKOFF_MIN, BACKOFF_MAX = 1.0, 60.0


class PairingFailed(Exception):
    pass


def ws_url_for(coordinator_url: str) -> str:
    return coordinator_url.replace("https://", "wss://").replace(
        "http://", "ws://"
    ).rstrip("/") + "/ws/agent"


async def redeem_pairing(
    coordinator_url: str, code: str, agent_version: str
) -> dict:
    """Exchange a pairing code for a device_id + scoped credential."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{coordinator_url.rstrip('/')}/api/v1/pairing/redeem",
            json={"code": code.strip().upper(), "agent_version": agent_version},
        )
    if r.status_code != 200:
        detail = r.json().get("detail", {})
        raise PairingFailed(detail.get("error", f"pairing failed: {r.status_code}"))
    return r.json()


def backoff_delays() -> "iter[float]":
    """Exponential backoff with jitter, capped at BACKOFF_MAX."""
    delay = BACKOFF_MIN
    while True:
        yield delay
        delay = min(delay * 2, BACKOFF_MAX) * (0.5 + random.random() * 0.5)


async def _heartbeat(ws, device_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        await ws.send(Envelope(type=MessageType.PING).model_dump_json())


async def _handle_message(raw: str, ws, send) -> None:
    env = Envelope.model_validate_json(raw)
    if env.type is MessageType.PING:
        await send(Envelope(type=MessageType.PONG).model_dump_json())
    elif env.type is MessageType.COMMAND_DISPATCH:
        # Phase 3: route to the operations engine. For now, fail loudly
        # rather than silently dropping work.
        await send(Envelope(
            type=MessageType.COMMAND_RESULT,
            payload={
                "task_id": env.payload.get("task_id", ""),
                "step_id": env.payload.get("step_id", ""),
                "ok": False,
                "error": "command execution not yet implemented (Phase 3)",
            },
        ).model_dump_json())
    elif env.type is MessageType.ERROR:
        log.warning("coordinator error: %s", env.payload)


async def run_session(
    coordinator_url: str,
    device_id: str,
    credential: str,
    agent_version: str,
    status: DeviceStatus = DeviceStatus.ONLINE,
) -> None:
    """One connection attempt: hello → message loop. Raises on failure;
    the caller (run_forever) owns retry/backoff policy."""
    url = ws_url_for(coordinator_url)
    async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
        hello = Envelope(
            type=MessageType.AGENT_HELLO,
            payload=AgentHello(
                device_id=device_id,
                device_credential=credential,
                agent_version=agent_version,
                status=status,
            ).model_dump(),
        )
        await ws.send(hello.model_dump_json())

        ack_raw = await asyncio.wait_for(ws.recv(), timeout=HELLO_ACK_TIMEOUT)
        ack = Envelope.model_validate_json(ack_raw)
        if ack.type is MessageType.ERROR:
            raise RuntimeError(f"handshake rejected: {ack.payload}")
        if ack.type is not MessageType.PONG:
            raise RuntimeError(f"unexpected handshake reply: {ack.type}")
        log.info("connected to %s", url)

        hb = asyncio.create_task(_heartbeat(ws, device_id))
        try:
            async for raw in ws:
                try:
                    await _handle_message(raw, ws, ws.send)
                except Exception:
                    log.exception("failed to handle message")
        finally:
            hb.cancel()


async def run_forever(
    coordinator_url: str,
    device_id: str,
    credential: str,
    agent_version: str,
) -> None:
    """Reconnecting outer loop — the agent's main resident coroutine."""
    delays = backoff_delays()
    while True:
        try:
            await run_session(
                coordinator_url, device_id, credential, agent_version
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            delay = next(delays)
            log.warning("connection lost (%s); retrying in %.0fs", exc, delay)
            await asyncio.sleep(delay)
        else:
            delays = backoff_delays()  # clean disconnect: reset backoff
