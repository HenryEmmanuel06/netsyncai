"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity as ActivityIcon, Bot, CloudOff, Download, FilePlus2, FolderPlus,
  History, Monitor, Pencil, RefreshCw, ServerCrash, Share2, Tag, Trash2, UserPlus,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { Dropdown, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { basename, formatDate, timeAgo } from "@/lib/format";
import type { ActivityItem } from "@/types";

const ICONS: Record<string, React.ReactNode> = {
  "device.paired": <Monitor size={15} />,
  "device.online": <Monitor size={15} />,
  "device.offline": <CloudOff size={15} />,
  "device.removed": <ServerCrash size={15} />,
  "folder.added": <FolderPlus size={15} />,
  "folder.removed": <FolderPlus size={15} />,
  "folder.access_changed": <FolderPlus size={15} />,
  "share.created": <Share2 size={15} />,
  "share.deleted": <Share2 size={15} />,
  "grant.added": <UserPlus size={15} />,
  "grant.revoked": <UserPlus size={15} />,
  "file.renamed": <Pencil size={15} />,
  "file.moved": <Pencil size={15} />,
  "file.copied": <FilePlus2 size={15} />,
  "file.folder_created": <FolderPlus size={15} />,
  "file.deleted": <Trash2 size={15} />,
  "file.downloaded": <Download size={15} />,
  "file.uploaded": <FilePlus2 size={15} />,
  "sync.started": <RefreshCw size={15} />,
  "sync.pause": <RefreshCw size={15} />,
  "sync.resume": <RefreshCw size={15} />,
  "sync.stop": <RefreshCw size={15} />,
  "ai.task": <Bot size={15} />,
};

const LABELS: Record<string, string> = {
  "device.paired": "Computer connected",
  "device.online": "Computer came online",
  "device.offline": "Computer went offline",
  "device.removed": "Computer removed",
  "folder.added": "Folder shared",
  "folder.removed": "Folder unshared",
  "folder.access_changed": "Folder access changed",
  "share.created": "Share created",
  "share.deleted": "Share removed",
  "grant.added": "Access granted",
  "grant.revoked": "Access revoked",
  "file.renamed": "File renamed",
  "file.moved": "File moved",
  "file.copied": "File copied",
  "file.folder_created": "Folder created",
  "file.deleted": "File deleted",
  "file.downloaded": "File downloaded",
  "file.uploaded": "File uploaded",
  "sync.started": "Sync started",
  "sync.pause": "Sync paused",
  "sync.resume": "Sync resumed",
  "sync.stop": "Sync stopped",
  "ai.task": "AI task",
};

export default function ActivityPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<ActivityItem[] | null>(null);
  const [limit, setLimit] = useState(50);
  const [typeFilter, setTypeFilter] = useState("all");

  const load = useCallback(async () => {
    if (!token) return;
    const r = await apiFetch<ActivityItem[]>(`/api/v1/activity?limit=${limit}`, token);
    setItems(r);
  }, [token, limit]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Activity" subtitle="Everything that happened across your network." />
      {items && items.length > 0 && (
        <div className="mb-4">
          <Dropdown className="w-44 text-xs" value={typeFilter}
            onChange={setTypeFilter}
            options={[
              { value: "all", label: "All activities" },
              { value: "device", label: "Devices" },
              { value: "file", label: "Files" },
              { value: "folder", label: "Folders" },
              { value: "share", label: "Sharing" },
              { value: "sync", label: "Sync" },
              { value: "ai", label: "AI tasks" },
            ]} />
        </div>
      )}
      {items === null ? (
        <div className="py-16 text-center"><Spinner /></div>
      ) : items.length === 0 ? (
        <EmptyState icon={<History size={20} />} title="No activity yet"
          hint="Pair a computer and share a folder — everything you do is recorded here." />
      ) : (
        <div className="card divide-y divide-[var(--color-border)]">
          {items.filter((a) => typeFilter === "all" || a.action.startsWith(typeFilter + ".")).map((a) => (
            <div key={a.id} className="flex items-center gap-3 px-4 py-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--color-surface-2)] text-[var(--color-accent)]">
                {ICONS[a.action] ?? <ActivityIcon size={15} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm">{LABELS[a.action] ?? a.action}</div>
                {a.target && (
                  <div className="truncate text-xs text-[var(--color-text-dim)]">{a.target}</div>
                )}
              </div>
              <div className="shrink-0 text-xs text-[var(--color-text-dim)]" title={formatDate(a.created_at)}>
                {timeAgo(a.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}
      {items && items.length >= limit && (
        <button className="btn btn-ghost mx-auto mt-4" onClick={() => setLimit((n) => n + 50)}>
          Load more
        </button>
      )}
    </div>
  );
}
