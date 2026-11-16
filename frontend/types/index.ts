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
  file_id: string;
  rel_path: string;
  name: string;
  ext: string;
  size: number;
  mtime: number;
  is_dir?: boolean;
}
