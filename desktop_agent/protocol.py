"""NetSync wire protocol — shared message schemas.

Vendored by cloud_backend and desktop_agent so both sides serialize
identically. Wire format is versioned via `Envelope.v`.

Phase 1 scope: envelope + presence + command dispatch/result only.
Transfer/sync message types land with their phases.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 1


class MessageType(str, Enum):
    # agent -> cloud
    AGENT_HELLO = "agent.hello"
    PRESENCE_UPDATE = "presence.update"
    COMMAND_RESULT = "command.result"
    # cloud -> agent
    COMMAND_DISPATCH = "command.dispatch"
    # file transfer (either direction)
    TRANSFER_BEGIN = "transfer.begin"
    TRANSFER_CHUNK = "transfer.chunk"
    TRANSFER_END = "transfer.end"
    TRANSFER_ABORT = "transfer.abort"
    # bidirectional
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class Envelope(BaseModel):
    v: int = PROTOCOL_VERSION
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType
    ts: float = Field(default_factory=time.time)
    payload: dict[str, Any] = Field(default_factory=dict)


class DeviceStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    INVISIBLE = "invisible"
    OFFLINE = "offline"


class AgentHello(BaseModel):
    """First message an agent sends after the WS upgrade."""
    device_id: str
    device_credential: str  # scoped credential issued at pairing time
    agent_version: str
    status: DeviceStatus = DeviceStatus.ONLINE
    lan_address: str | None = None
    lan_port: int | None = None


class PresenceUpdate(BaseModel):
    device_id: str
    status: DeviceStatus


class CommandDispatch(BaseModel):
    """Coordinator -> agent. `tool` must be one of the fixed tool names."""
    task_id: str
    step_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    """Agent -> coordinator."""
    task_id: str
    step_id: str
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ErrorPayload(BaseModel):
    code: str
    message: str
    retryable: bool = False


# ── file transfer ────────────────────────────────────────────────────────────
# Chunks flow over the established WSS (relay transport). A later phase adds
# direct LAN P2P behind the same TRANSFER_* contract — payload is identical.

class TransferBegin(BaseModel):
    transfer_id: str
    direction: Literal["push", "pull"]   # push = sender→receiver, pull = agent→cloud relay
    name: str
    size: int
    sha256: str
    meta: dict[str, Any] = Field(default_factory=dict)


class TransferChunk(BaseModel):
    transfer_id: str
    seq: int
    data: str   # base64


class TransferEnd(BaseModel):
    transfer_id: str
    seq: int          # total chunks sent
    sha256: str


class TransferAbort(BaseModel):
    transfer_id: str
    reason: str


# permission bits — mirrors supabase migration comment
PERM_BROWSE = 1
PERM_DOWNLOAD = 2
PERM_UPLOAD = 4
PERM_RENAME = 8
PERM_EDIT = 16
PERM_MOVE = 32
PERM_DELETE = 64
PERM_CREATE_FOLDER = 128
PERM_START_SYNC = 256
PERM_MANAGE_SYNC = 512
PERM_MANAGE_SHARING = 1024


# Predefined AI/manual tool names — the ONLY operations the task engine may
# emit. Agents must reject anything not in this set.
TOOL_NAMES: frozenset[str] = frozenset({
    "search_files", "browse_folder", "download_file", "send_file",
    "rename_file", "move_file", "copy_file", "delete_file", "create_folder",
    "convert_document", "start_sync", "pause_sync", "resume_sync",
    "stop_sync", "get_device_status", "get_transfer_status",
})

ToolName = Literal[
    "search_files", "browse_folder", "download_file", "send_file",
    "rename_file", "move_file", "copy_file", "delete_file", "create_folder",
    "convert_document", "start_sync", "pause_sync", "resume_sync",
    "stop_sync", "get_device_status", "get_transfer_status",
]
