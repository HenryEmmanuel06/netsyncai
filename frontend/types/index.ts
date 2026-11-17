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
  path?: string;            // absolute — preferred for operations
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

export interface SharedFolder {
  id: string;
  owner_id: string;
  device_id: string;
  device_name: string;
  label: string;
  root_path: string;
  created_at?: string;
  permissions?: number;
  grant_id?: string;
  owner_email?: string | null;
}

export interface LocalDirEntry {
  name: string;
  path: string;
  kind: "dir" | "drive" | "quick" | "file";
  blocked?: string | null;
}

export interface SharedFolderInfo {
  id: number;
  path: string;
  label: string;
  access: string;
  file_count: number;
  total_size: number;
  indexing?: boolean;
  last_indexed_at?: string | null;
}

export interface GrantEntry {
  id: string;
  folder_id: string;
  subject_user_id: string;
  permissions_granted: number;
  created_at?: string;
}

export interface ActivityItem {
  id: number;
  action: string;
  target?: string | null;
  device_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface TaskResult {
  summary: string | null;
  needs_confirmation: boolean;
  executed: boolean;
  steps: TaskStep[];
}
