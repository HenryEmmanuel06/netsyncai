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

from protocol import AgentHello, CommandDispatch, DeviceStatus, Envelope, MessageType

log = logging.getLogger("netsync.coordinator")

HEARTBEAT_SECONDS = 30
HELLO_ACK_TIMEOUT = 10.0
BACKOFF_MIN, BACKOFF_MAX = 1.0, 60.0


class PairingFailed(Exception):
    pass


class CredentialRejected(Exception):
    """The coordinator no longer accepts this device (revoked / unknown).
    Retrying is pointless — the agent must be paired again."""


def _notify(cb, state: str, detail: str | None = None) -> None:
    if cb is not None:
        try:
            cb(state, detail)
        except Exception:
            log.exception("status callback failed")


def ws_url_for(coordinator_url: str) -> str:
    return coordinator_url.replace("https://", "wss://").replace(
        "http://", "ws://"
    ).rstrip("/") + "/ws/agent"


async def redeem_pairing(
    coordinator_url: str, code: str, agent_version: str,
    machine_id: str = "",
) -> dict:
    """Exchange a pairing code for a device_id + scoped credential."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{coordinator_url.rstrip('/')}/api/v1/pairing/redeem",
            json={"code": code.strip().upper(), "agent_version": agent_version,
                  "machine_id": machine_id},
        )
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", {})
            msg = detail.get("error", f"pairing failed: {r.status_code}") \
                if isinstance(detail, dict) else str(detail)
        except Exception:
            msg = f"pairing failed: {r.status_code}"
        raise PairingFailed(msg)
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


async def _run_command(ctx, env: Envelope, send) -> None:
    """Execute a dispatched tool command and report the result."""
    from file_operations.ops import HANDLERS, OpDenied

    cmd = CommandDispatch.model_validate(env.payload)
    handler = HANDLERS.get(cmd.tool)
    try:
        if handler is None:
            raise OpDenied(f"unknown tool: {cmd.tool}")
        result = await handler(ctx, cmd.args)
        payload = {"task_id": cmd.task_id, "step_id": cmd.step_id,
                   "ok": True, "result": result}
    except OpDenied as exc:
        payload = {"task_id": cmd.task_id, "step_id": cmd.step_id,
                   "ok": False, "error": str(exc)}
    except Exception as exc:  # never let an op crash the session
        log.exception("command %s failed", cmd.tool)
        payload = {"task_id": cmd.task_id, "step_id": cmd.step_id,
                   "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    await send(Envelope(type=MessageType.COMMAND_RESULT, payload=payload).model_dump_json())


def _watch_task(t: asyncio.Task) -> None:
    if not t.cancelled() and (exc := t.exception()):
        log.error("handler task failed: %s", exc)


TRANSFER_TYPES = {
    MessageType.TRANSFER_BEGIN, MessageType.TRANSFER_CHUNK,
    MessageType.TRANSFER_END, MessageType.TRANSFER_ABORT,
}


async def _handle_message(raw: str, send, ctx=None, tasks=None) -> None:
    env = Envelope.model_validate_json(raw)
    if env.type is MessageType.PING:
        await send(Envelope(type=MessageType.PONG).model_dump_json())
    elif env.type is MessageType.COMMAND_DISPATCH:
        if ctx is not None:
            # run concurrently — a send_file handler blocks on chunks
            t = asyncio.create_task(_run_command(ctx, env, send))
            if tasks is not None:
                tasks.add(t)
                t.add_done_callback(_watch_task)
                t.add_done_callback(tasks.discard)
        else:
            await send(Envelope(
                type=MessageType.COMMAND_RESULT,
                payload={
                    "task_id": env.payload.get("task_id", ""),
                    "step_id": env.payload.get("step_id", ""),
                    "ok": False,
                    "error": "command execution not available",
                },
            ).model_dump_json())
    elif env.type in TRANSFER_TYPES:
        if ctx is not None:
            state = ctx.transfer_state(env.payload["transfer_id"])
            if env.type is MessageType.TRANSFER_BEGIN:
                p = env.payload
                state.name = state.name or p.get("name", "")
                state.size = p.get("size", 0) or state.size
                state.meta = p.get("meta") or {}
                state.direction = "in"
            elif env.type is MessageType.TRANSFER_CHUNK:
                # base64 inflates by 4/3 — close enough for a progress bar
                state.received += (len(env.payload["data"]) * 3) // 4
            await state.queue.put(env)
    elif env.type is MessageType.SYNC_EVENT:
        if ctx is not None:
            # task: _apply_write blocks on transfer chunks, which only
            # flow while the read loop stays free
            t = asyncio.create_task(ctx.sync.on_sync_event(env))
            if tasks is not None:
                tasks.add(t)
                t.add_done_callback(_watch_task)
                t.add_done_callback(tasks.discard)
    elif env.type is MessageType.SYNC_REQUEST:
        if ctx is not None:
            t = asyncio.create_task(ctx.sync.on_sync_request(env))
            if tasks is not None:
                tasks.add(t)
                t.add_done_callback(_watch_task)
                t.add_done_callback(tasks.discard)
    elif env.type is MessageType.ERROR:
        log.warning("coordinator error: %s", env.payload)


async def run_session(
    coordinator_url: str,
    device_id: str,
    credential: str,
    agent_version: str,
    status: DeviceStatus = DeviceStatus.ONLINE,
    conn=None,
    on_status=None,
    machine_id: str = "",
) -> None:
    """One connection attempt: hello → message loop. Raises on failure;
    the caller (run_forever) owns retry/backoff policy."""
    url = ws_url_for(coordinator_url)
    _notify(on_status, "connecting")
    async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
        hello = Envelope(
            type=MessageType.AGENT_HELLO,
            payload=AgentHello(
                device_id=device_id,
                device_credential=credential,
                agent_version=agent_version,
                status=status,
                machine_id=machine_id or None,
            ).model_dump(),
        )
        await ws.send(hello.model_dump_json())

        ack_raw = await asyncio.wait_for(ws.recv(), timeout=HELLO_ACK_TIMEOUT)
        ack = Envelope.model_validate_json(ack_raw)
        if ack.type is MessageType.ERROR:
            if ack.payload.get("code") in ("auth_failed", "revoked"):
                raise CredentialRejected(ack.payload.get("message", "rejected"))
            raise RuntimeError(f"handshake rejected: {ack.payload}")
        if ack.type is not MessageType.PONG:
            raise RuntimeError(f"unexpected handshake reply: {ack.type}")
        log.info("connected to %s", url)
        _notify(on_status, "online")

        ctx = None
        periodic = None
        if conn is not None:
            from file_operations.folders import FOLDER_HANDLERS, periodic_reindex
            from file_operations.ops import AgentContext, HANDLERS
            from synchronization.sync_engine import SYNC_HANDLERS, SyncEngine
            ctx = AgentContext(conn, ws.send)
            ctx.sync = SyncEngine(ctx, device_id)
            HANDLERS.update(SYNC_HANDLERS)
            HANDLERS.update(FOLDER_HANDLERS)
            periodic = asyncio.create_task(periodic_reindex(ctx))

        hb = asyncio.create_task(_heartbeat(ws, device_id))
        tasks: set = set()
        try:
            async for raw in ws:
                try:
                    await _handle_message(raw, ws.send, ctx, tasks)
                except Exception:
                    log.exception("failed to handle message")
        finally:
            hb.cancel()
            if periodic is not None:
                periodic.cancel()
            for t in tasks:
                t.cancel()
            if ctx is not None:
                ctx.sync.stop_all()
                for t in ctx.background:
                    t.cancel()


async def run_forever(
    coordinator_url: str | list[str],
    device_id: str,
    credential: str,
    agent_version: str,
    conn=None,
    on_status=None,
    machine_id: str = "",
) -> None:
    """Reconnecting outer loop — the agent's main resident coroutine.
    Raises CredentialRejected when the device must be re-paired.

    `coordinator_url` may be a single URL or a failover list — on a lost
    connection the agent rotates to the next backend before backing off,
    so a dead primary fails over to a self-hosted secondary."""
    urls = [coordinator_url] if isinstance(coordinator_url, str) else list(coordinator_url)
    delays = backoff_delays()
    idx = 0
    while True:
        url = urls[idx % len(urls)]
        try:
            await run_session(
                url, device_id, credential, agent_version,
                conn=conn, on_status=on_status, machine_id=machine_id,
            )
        except (asyncio.CancelledError, CredentialRejected) as exc:
            if isinstance(exc, CredentialRejected):
                log.error("coordinator rejected this device: %s", exc)
                _notify(on_status, "rejected", str(exc))
            raise
        except Exception as exc:
            delay = next(delays)
            if len(urls) > 1:
                idx += 1
                log.warning("%s unreachable (%s); trying %s in %.0fs",
                            url, exc, urls[idx % len(urls)], delay)
            else:
                log.warning("connection lost (%s); retrying in %.0fs", exc, delay)
            _notify(on_status, "offline", str(exc))
            await asyncio.sleep(delay)
        else:
            _notify(on_status, "offline")
            idx = 0                      # back to primary on next connect
            delays = backoff_delays()    # clean disconnect: reset backoff
