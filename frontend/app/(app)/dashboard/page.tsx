"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity as ActivityIcon, ArrowRight, Bot, CloudOff, FolderSearch,
  Monitor, RefreshCw, Search, Send, ServerCrash, Share2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { FileIcon, Spinner, StatusDot } from "@/components/ui";
import { basename, formatBytes, formatDate, timeAgo } from "@/lib/format";
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
  "sync.started": <RefreshCw size={14} />,
  "ai.task": <Bot size={14} />,
};

export default function Dashboard() {
  const { token, email } = useAuth();
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
      apiFetch<ActivityItem[]>("/api/v1/activity?limit=8", token).catch(() => []),
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

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_340px]">
      {/* ── center ── */}
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">
          {greeting}, {firstName}
        </h1>
        <p className="mt-1 text-sm text-[var(--color-text-dim)]">
          Manage files, run tasks, and share across your connected computers.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { href: "/files", icon: <FolderSearch size={18} />, title: "Find & Get Files", sub: "Browse every computer" },
            { href: "/sync", icon: <RefreshCw size={18} />, title: "Sync Folders", sub: "Keep folders in sync" },
            { href: "/permissions", icon: <Share2 size={18} />, title: "Share a Folder", sub: "Grant people access" },
            { href: "/assistant", icon: <Bot size={18} />, title: "Run Tasks", sub: "Multi-step automation" },
          ].map((a) => (
            <Link key={a.title} href={a.href}
              className="card card-hover group flex flex-col gap-2 p-4">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)] transition-transform group-hover:scale-105">
                {a.icon}
              </span>
              <div>
                <div className="text-sm font-semibold">{a.title}</div>
                <div className="text-xs text-[var(--color-text-dim)]">{a.sub}</div>
              </div>
            </Link>
          ))}
        </div>

        <form onSubmit={searchAll} className="card mt-5 flex items-center gap-3 p-3">
          <Search size={16} className="ml-1 shrink-0 text-[var(--color-text-dim)]" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search files across all computers…"
            className="flex-1 bg-transparent text-sm outline-none"
          />
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
                No matches — files only appear in search after a folder is
                shared on that computer.
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
                    <span className="hidden max-w-[40%] truncate text-xs text-[var(--color-text-dim)] md:block">
                      {f.path}
                    </span>
                    <span className="w-16 text-right text-xs text-[var(--color-text-dim)]">
                      {formatBytes(f.size)}
                    </span>
                    <a className="text-xs text-[var(--color-accent)] hover:underline"
                      href={`/files?device=${d.device_id}&path=${encodeURIComponent(f.path)}`}>
                      Open
                    </a>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── right rail ── */}
      <div className="space-y-4">
        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <RefreshCw size={15} className="text-[var(--color-accent)]" /> Synchronization
            </h3>
            <Link href="/sync" className="btn btn-ghost !px-2.5 !py-1 text-xs">+ New sync</Link>
          </div>
          <div className="space-y-2.5">
            {activeSyncs.slice(0, 4).map((s) => (
              <div key={s.id} className="flex items-start justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <div className="truncate font-medium">{basename(s.participants[0]?.root ?? s.name)}</div>
                  <div className="truncate text-xs text-[var(--color-text-dim)]">
                    {basename(s.participants[0]?.root ?? "")} ↔ {basename(s.participants[1]?.root ?? "")}
                  </div>
                </div>
                <span className="badge badge-green">In sync</span>
              </div>
            ))}
            {syncs.filter((s) => s.state === "paused").slice(0, 2).map((s) => (
              <div key={s.id} className="flex items-start justify-between gap-2 text-sm">
                <div className="truncate font-medium">{basename(s.participants[0]?.root ?? s.name)}</div>
                <span className="badge badge-amber">Paused</span>
              </div>
            ))}
            {syncs.length === 0 && (
              <p className="text-xs text-[var(--color-text-dim)]">
                No sync sessions yet — link two folders to keep them identical.
              </p>
            )}
          </div>
        </div>

        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <ActivityIcon size={15} className="text-[var(--color-accent)]" /> Recent activity
            </h3>
            <Link href="/activity" className="text-xs text-[var(--color-accent)] hover:underline">
              View all
            </Link>
          </div>
          <div className="space-y-3">
            {activity.slice(0, 6).map((a) => (
              <div key={a.id} className="flex items-start gap-2.5 text-xs">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[var(--color-surface-2)] text-[var(--color-accent)]">
                  {ACTION_ICONS[a.action.split(".")[0] + "." + (a.action.split(".")[1] ?? "")] ??
                    ACTION_ICONS[a.action] ?? <ActivityIcon size={14} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate">{a.action.replace(/\./g, " ")}</div>
                  <div className="truncate text-[var(--color-text-dim)]">
                    {a.target ? basename(a.target) : ""} · {timeAgo(a.created_at)}
                  </div>
                </div>
              </div>
            ))}
            {activity.length === 0 && (
              <p className="text-xs text-[var(--color-text-dim)]">Nothing yet — activity appears as you use NetSync.</p>
            )}
          </div>
        </div>

        <div className="card p-4">
          <h3 className="mb-3 text-sm font-semibold">Network overview</h3>
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { v: online.length, l: "online" },
              { v: devices.length, l: "computers" },
              { v: activeSyncs.length, l: "syncs" },
            ].map((s) => (
              <div key={s.l} className="rounded-lg bg-[var(--color-surface-2)] py-3">
                <div className="text-lg font-semibold">{s.v}</div>
                <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-dim)]">{s.l}</div>
              </div>
            ))}
          </div>
          {online.length === 0 && devices.length > 0 && (
            <p className="mt-3 text-xs text-[var(--color-warn)]">
              All your computers are offline — open NetSync AI on one of them.
            </p>
          )}
          {devices.length === 0 && (
            <Link href="/devices" className="mt-3 flex items-center gap-1 text-xs text-[var(--color-accent)] hover:underline">
              Connect your first computer <ArrowRight size={12} />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
