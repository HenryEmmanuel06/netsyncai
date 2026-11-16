"""Agent WebSocket endpoint — the persistent agent-initiated link.

Handshake: agent connects → sends Envelope(agent.hello) with device_id +
credential within 10s → verified → session opens, device goes online.
Then: agent pings (heartbeat) and can send presence.update; the server
may push command.dispatch (Phase 3+). Any disconnect → device offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_device_store
from app.networking.connections import manager
from app.networking import transfers
from app.orchestration import dispatcher
from app.schemas.devices import DeviceResponse
from app.services.activity import log_activity
from app.services.device_registry import DeviceNotFound, DeviceStore
from app.protocol import (
    AgentHello,
    CommandDispatch,
    Envelope,
    ErrorPayload,
    MessageType,
    PresenceUpdate,
)

log = logging.getLogger("netsync.ws_agent")

router = APIRouter()

HELLO_TIMEOUT = 10.0


def _env(msg_type: MessageType, payload: dict) -> str:
    return Envelope(type=msg_type, payload=payload).model_dump_json()


async def _close(ws: WebSocket, code: int, error_code: str, message: str) -> None:
    try:
        await ws.send_text(_env(
            MessageType.ERROR,
            ErrorPayload(code=error_code, message=message).model_dump(),
        ))
    finally:
        await ws.close(code=code)


@router.websocket("/ws/agent")
async def agent_socket(
    ws: WebSocket,
    store: DeviceStore = Depends(get_device_store),
) -> None:
    await ws.accept()
    device: DeviceResponse | None = None
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=HELLO_TIMEOUT)
        env = Envelope.model_validate_json(raw)
        if env.type is not MessageType.AGENT_HELLO:
            await _close(ws, 4400, "protocol_error", "first message must be agent.hello")
            return
        hello = AgentHello.model_validate(env.payload)

        try:
            device = await store.get_device_by_id(hello.device_id)
        except DeviceNotFound:
            await _close(ws, 4401, "auth_failed", "unknown device")
            return
        if device.revoked_at is not None:
            await _close(ws, 4403, "revoked", "device has been revoked")
            return
        if not await store.verify_device_credential(hello.device_id, hello.device_credential):
            await _close(ws, 4401, "auth_failed", "invalid device credential")
            return

        await store.agent_connected(
            device.id, hello.status.value, hello.agent_version,
            hello.lan_address, hello.lan_port,
        )
        manager.register(device.id, ws)
        await ws.send_text(_env(MessageType.PONG, {"session": "ready"}))
        log.info("device %s connected (%s)", device.id, device.name)
        await log_activity(store, device.owner_id, "device.online",
                           device_id=device.id, target=device.name)

        # re-issue active sync sessions — agents drop watchers on disconnect
        for s in await store.get_active_syncs_for_device(device.id):
            try:
                await manager.send(device.id, _env(
                    MessageType.COMMAND_DISPATCH,
                    CommandDispatch(
                        task_id="sync-rejoin", step_id=str(uuid.uuid4()),
                        tool="start_sync", args=s,
                    ).model_dump(),
                ))
            except Exception:
                pass

        while True:
            raw = await ws.receive_text()
            env = Envelope.model_validate_json(raw)
            if env.type is MessageType.PING:
                await ws.send_text(_env(MessageType.PONG, {}))
            elif env.type is MessageType.PRESENCE_UPDATE:
                upd = PresenceUpdate.model_validate(env.payload)
                await store.set_status(device.owner_id, device.id, upd.status.value)
            elif env.type is MessageType.COMMAND_RESULT:
                dispatcher.resolve(
                    env.payload.get("step_id", ""), env.payload
                )
            elif env.type in (
                MessageType.TRANSFER_BEGIN,
                MessageType.TRANSFER_CHUNK,
                MessageType.TRANSFER_END,
                MessageType.TRANSFER_ABORT,
            ):
                await transfers.route(env, raw)
            elif env.type is MessageType.SYNC_EVENT:
                # relay to every other participant device in the session
                for p in await store.get_sync_participants(env.payload["session_id"]):
                    if p["device_id"] != env.payload["from_device"]:
                        await manager.send(p["device_id"], raw)
            elif env.type is MessageType.SYNC_REQUEST:
                await manager.send(env.payload["origin_device"], raw)
            else:
                await ws.send_text(_env(
                    MessageType.ERROR,
                    ErrorPayload(
                        code="unsupported_type",
                        message=f"unhandled message type {env.type}",
                    ).model_dump(),
                ))

    except WebSocketDisconnect:
        pass
    except (asyncio.TimeoutError, json.JSONDecodeError, ValueError):
        await _close(ws, 4400, "protocol_error", "invalid handshake")
    finally:
        if device is not None:
            manager.unregister(device.id)
            await store.agent_disconnected(device.id)
            log.info("device %s disconnected", device.id)
            await log_activity(store, device.owner_id, "device.offline",
                               device_id=device.id, target=device.name)
