/**
 * NetSync wire protocol — TypeScript mirror of shared/protocol/messages.py.
 * Keep in sync when the Python side changes.
 */

export const PROTOCOL_VERSION = 1;

export type DeviceStatus = "online" | "busy" | "invisible" | "offline";

export type MessageType =
  | "agent.hello"
  | "presence.update"
  | "command.result"
  | "command.dispatch"
  | "error"
  | "ping"
  | "pong";

export interface Envelope<T = Record<string, unknown>> {
  v: number;
  id: string;
  type: MessageType;
  ts: number;
  payload: T;
}

export interface AgentHello {
  device_id: string;
  device_credential: string;
  agent_version: string;
  status: DeviceStatus;
  lan_address?: string;
  lan_port?: number;
}

export interface PresenceUpdate {
  device_id: string;
  status: DeviceStatus;
}

export interface CommandDispatch {
  task_id: string;
  step_id: string;
  tool: ToolName;
  args: Record<string, unknown>;
}

export interface CommandResult {
  task_id: string;
  step_id: string;
  ok: boolean;
  result: Record<string, unknown>;
  error?: string;
}

export const TOOL_NAMES = [
  "search_files", "browse_folder", "download_file", "send_file",
  "rename_file", "move_file", "copy_file", "delete_file", "create_folder",
  "convert_document", "start_sync", "pause_sync", "resume_sync",
  "stop_sync", "get_device_status", "get_transfer_status",
] as const;

export type ToolName = (typeof TOOL_NAMES)[number];
