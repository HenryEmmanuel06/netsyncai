"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity as ActivityIcon, ArrowRight, ArrowLeftRight, Bot, CloudOff,
  FolderSearch, FolderSync, Monitor, RefreshCw, Search, Send, ServerCrash,
  Share2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useTransfers } from "@/components/TransferCenter";
import { FileIcon, Spinner, StatCard, StatusDot } from "@/components/ui";
import { basename, formatBytes, timeAgo } from "@/lib/format";
import type { ActivityItem, Device, SyncSession } from "@/types";

interface AllSearchResult {
  device_id: string;
  device_name: string;
  status: string;
  results: { name: string; path: string; size: number; mtime: number; is_dir?: boolean }[];
}

const ACTION_ICONS: Record<string, React.ReactNode> = {
  "device.paired": <Monitor size={14} />,
  "device.online": <Monitor size={14} />,
  "device.offline": <CloudOff size={14} />,
  "device.removed": <ServerCrash size={14} />,
  "folder.added": <Share2 size={14} />,
  "folder.removed": <Share2 size={14} />,
  "share.created": <Share2 size={14} />,
  "grant.added": <Share2 size={14} />,
  "grant.revoked": <Share2 size={14} />,
  "sync.started": <RefreshCw size={14} />,
  "file.uploaded": <ArrowLeftRight size={14} />,
  "file.downloaded": <ArrowLeftRight size={14} />,
  "ai.task": <Bot size={14} />,
};

const ACTION_LABELS: Record<string, string> = {
  "device.paired": "Computer connected",
  "device.online": "Came online",
  "device.offline": "Went offline",
  "device.removed": "Computer removed",
  "folder.added": "Folder shared",
  "folder.removed": "Folder unshared",
  "share.created": "Share created",
  "share.deleted": "Share removed",
  "grant.added": "Access granted",
  "grant.revoked": "Access revoked",
  "file.downloaded": "File downloaded",
  "file.uploaded": "File uploaded",
  "file.renamed": "File renamed",
  "file.deleted": "File deleted",
  "sync.started": "Sync started",
  "ai.task": "AI task",
};

export default function Dashboard() {
  const { token, email } = useAuth();
  const { transfers } = useTransfers();
  const [devices, setDevices] = useState<Device[]>([]);
  const [syncs, setSyncs] = useState<SyncSession[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [allResults, setAllResults] = useState<AllSearchResult[] | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    const [d, s, a] = await Promise.all([
      apiFetch<Device[]>("/api/v1/devices", token),
      apiFetch<SyncSession[]>("/api/v1/sync", token).catch(() => []),
      apiFetch<ActivityItem[]>("/api/v1/activity?limit=20", token).catch(() => []),
    ]);
    setDevices(d.filter((x) => !x.revoked_at));
    setSyncs(s.filter((x) => x.state !== "stopped"));
    setActivity(a);
  }, [token]);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  async function searchAll(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim() || !token) return;
    setSearching(true);
    try {
      const r = await apiFetch<{ devices: AllSearchResult[] }>(
        `/api/v1/files/search-all?q=${encodeURIComponent(q)}`, token,
      );
      setAllResults(r.devices.filter((d) => d.results.length > 0 || d.status === "online"));
    } finally {
      setSearching(false);
    }
  }

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const firstName = (email ?? "there").split("@")[0];
  const online = devices.filter((d) => d.status === "online");
  const activeSyncs = syncs.filter((s) => s.state === "active");
  const today = new Date().toDateString();
  const todayActivity = activity.filter((a) => new Date(a.created_at).toDateString() === today);
  const ongoingTransfers = transfers.filter((t) => t.status === "active").length;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{greeting}, {firstName}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-dim)]">
            Your connected computers, sync status, and recent activity.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard tone="purple" icon={<Monitor size={20} />} value={online.length}
          label="Devices online" hint={`${devices.length} total`} />
        <StatCard tone="green" icon={<RefreshCw size={20} />} value={activeSyncs.length}
          label="Active syncs" />
        <StatCard tone="blue" icon={<ArrowLeftRight size={20} />} value={ongoingTransfers}
          label="Ongoing transfers" />
        <StatCard tone="amber" icon={<ActivityIcon size={20} />} value={todayActivity.length}
          label="Today's activities" />
      </div>

      <form onSubmit={searchAll} className="card mt-4 flex items-center gap-3 p-3">
        <Search size={16} className="ml-1 shrink-0 text-[var(--color-text-dim)]" />
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search files across all computers…"
          className="flex-1 bg-transparent text-sm outline-none" />
        <button className="btn btn-primary" disabled={searching || !q.trim()}>
          {searching ? <Spinner size={14} /> : <Send size={14} />} Search
        </button>
      </form>

      {allResults && (
        <div className="card mt-4 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
            <span className="text-sm font-medium">
              {allResults.reduce((n, d) => n + d.results.length, 0)} results
              across {allResults.length} computer{allResults.length === 1 ? "" : "s"}
            </span>
            <button onClick={() => setAllResults(null)}
              className="text-xs text-[var(--color-text-dim)] hover:text-[var(--color-text)]">Clear</button>
          </div>
          {allResults.length === 0 && (
            <div className="p-6 text-center text-sm text-[var(--color-text-dim)]">
              No matches — files only appear in search after a folder is shared on that computer.
            </div>
          )}
          {allResults.map((d) => (
            <div key={d.device_id}>
              <div className="flex items-center gap-2 bg-[var(--color-surface-2)] px-4 py-1.5 text-xs font-semibold text-[var(--color-text-dim)]">
                <StatusDot status={d.status} /> {d.device_name}
              </div>
              {d.results.slice(0, 10).map((f) => (
                <div key={f.path} className="flex items-center gap-3 border-t border-[var(--color-border)] px-4 py-2 text-sm">
                  <FileIcon name={f.name} isDir={f.is_dir} />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="hidden max-w-[40%] truncate text-xs text-[var(--color-text-dim)] md:block">{f.path}</span>
                  <span className="w-16 text-right text-xs text-[var(--color-text-dim)]">{formatBytes(f.size)}</span>
                  <a className="text-xs text-[var(--color-accent)] hover:underline"
                    href={`/files?device=${d.device_id}&path=${encodeURIComponent(f.path)}`}>Open</a>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {/* Connected devices */}
        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Connected computers</h3>
            <Link href="/devices" className="text-xs text-[var(--color-accent)] hover:underline">View all</Link>
          </div>
          <div className="space-y-2">
            {devices.slice(0, 5).map((d) => (
              <Link key={d.id} href="/devices"
                className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] px-3 py-2.5 transition-colors hover:border-[var(--color-accent)]">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-surface-2)]">
                  <Monitor size={16} className="text-[var(--color-accent)]" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{d.name}</div>
                  <div className="text-xs text-[var(--color-text-dim)]">
                    {d.status === "online" ? "Online" : `Last seen ${timeAgo(d.last_seen_at)}`}
                  </div>
                </div>
                <span className={`badge ${d.status === "online" ? "badge-green" : "badge-gray"}`}>{d.status}</span>
              </Link>
            ))}
            {devices.length === 0 && (
              <div className="rounded-lg border border-dashed border-[var(--color-border)] p-5 text-center text-xs text-[var(--color-text-dim)]">
                No computers yet —{" "}
                <Link href="/devices" className="text-[var(--color-accent)]">add your first one</Link>
              </div>
            )}
          </div>
        </div>

        {/* Recent activity */}
        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Recent activity</h3>
            <Link href="/activity" className="text-xs text-[var(--color-accent)] hover:underline">View all</Link>
          </div>
          <div className="space-y-3">
            {activity.slice(0, 6).map((a) => (
              <div key={a.id} className="flex items-start gap-2.5 text-xs">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-accent)]">
                  {ACTION_ICONS[a.action] ?? <ActivityIcon size={14} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate">{ACTION_LABELS[a.action] ?? a.action}</div>
                  <div className="truncate text-[var(--color-text-dim)]">
                    {a.target ? basename(a.target) : ""} · {timeAgo(a.created_at)}
                  </div>
                </div>
              </div>
            ))}
            {activity.length === 0 && (
              <p className="py-3 text-center text-xs text-[var(--color-text-dim)]">
                Nothing yet — activity appears as you use NetSync.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* quick actions */}
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { href: "/files", icon: <FolderSearch size={18} />, title: "Find & get files", sub: "Browse every computer" },
          { href: "/sync", icon: <FolderSync size={18} />, title: "Sync folders", sub: "Keep folders identical" },
          { href: "/permissions", icon: <Share2 size={18} />, title: "Share a folder", sub: "Grant people access" },
          { href: "/assistant", icon: <Bot size={18} />, title: "Ask the AI", sub: "Multi-step automation" },
        ].map((a) => (
          <Link key={a.title} href={a.href}
            className="card card-hover group flex items-center gap-3 p-4">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)] transition-transform group-hover:scale-105">
              {a.icon}
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{a.title}</div>
              <div className="truncate text-xs text-[var(--color-text-dim)]">{a.sub}</div>
            </div>
            <ArrowRight size={14} className="ml-auto text-[var(--color-text-dim)]" />
          </Link>
        ))}
      </div>
    </div>
  );
}
