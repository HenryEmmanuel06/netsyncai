/** Shared frontend types mirroring cloud_backend/app/schemas. */

export type DeviceStatus = "online" | "busy" | "invisible" | "offline";

export interface Device {
  id: string;
  owner_id: string;
  name: string;
  platform: string;
  agent_version: string | null;
  status: DeviceStatus;
  last_seen_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface RemoteFileEntry {
  file_id?: string;
  rel_path: string;
  name: string;
  ext?: string | null;
  size?: number | null;
  mtime?: number | null;
  is_dir?: boolean;
}

export interface SyncParticipant {
  device_id: string;
  root: string;
}

export interface SyncSession {
  id: string;
  name: string;
  mode: string;
  state: string;
  created_by: string;
  participants: SyncParticipant[];
}

export interface TaskStep {
  device: string | null;
  tool: string;
  args: Record<string, unknown>;
  description: string | null;
  ok?: boolean | null;
  result?: unknown;
  error?: string | null;
}

export interface TaskResult {
  summary: string | null;
  needs_confirmation: boolean;
  executed: boolean;
  steps: TaskStep[];
}
