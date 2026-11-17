"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import {
  Activity as ActivityIcon, ArrowRight, ArrowLeftRight, Bot, CloudOff,
  FolderSync, Monitor, RefreshCw, Search, ServerCrash, Share2, X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useTransfers } from "@/components/TransferCenter";
import {
  CardHeader, FileIcon, FolderArt, IconTile, Spinner, StatCard, StatusDot,
} from "@/components/ui";
import { basename, formatBytes, timeAgo } from "@/lib/format";
import type { ActivityItem, Device, SharedFolder, SyncSession } from "@/types";

interface AllSearchResult {
  device_id: string;
  device_name: string;
  status: string;
  results: { name: string; path: string; size: number; mtime: number; is_dir?: boolean }[];
}

const ACTION_ICONS: Record<string, React.ReactNode> = {
  "device.paired": <Monitor size={13} />,
  "device.online": <Monitor size={13} />,
  "device.offline": <CloudOff size={13} />,
  "device.removed": <ServerCrash size={13} />,
  "folder.added": <Share2 size={13} />,
  "folder.removed": <Share2 size={13} />,
  "share.created": <Share2 size={13} />,
  "grant.added": <Share2 size={13} />,
  "grant.revoked": <Share2 size={13} />,
  "sync.started": <RefreshCw size={13} />,
  "sync.requested": <RefreshCw size={13} />,
  "sync.accepted": <RefreshCw size={13} />,
  "file.uploaded": <ArrowLeftRight size={13} />,
  "file.downloaded": <ArrowLeftRight size={13} />,
  "ai.task": <Bot size={13} />,
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
  "sync.requested": "Sync requested",
  "sync.accepted": "Sync accepted",
  "sync.declined": "Sync declined",
  "ai.task": "AI task",
};

function DashboardInner() {
  const params = useSearchParams();
  const { token, email } = useAuth();
  const { transfers } = useTransfers();
  const [devices, setDevices] = useState<Device[]>([]);
  const [syncs, setSyncs] = useState<SyncSession[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [shares, setShares] = useState<{ owned: SharedFolder[]; granted: SharedFolder[] }>({ owned: [], granted: [] });
  const [q, setQ] = useState("");
  const [searching, setSearching] = useState(false);
  const [allResults, setAllResults] = useState<AllSearchResult[] | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    const [d, s, a, sh] = await Promise.all([
      apiFetch<Device[]>("/api/v1/devices", token),
      apiFetch<SyncSession[]>("/api/v1/sync", token).catch(() => []),
      apiFetch<ActivityItem[]>("/api/v1/activity?limit=20", token).catch(() => []),
      apiFetch<{ owned: SharedFolder[]; granted: SharedFolder[] }>("/api/v1/sharing", token)
        .catch(() => ({ owned: [], granted: [] })),
    ]);
    setDevices(d.filter((x) => !x.revoked_at));
    setSyncs(s.filter((x) => x.state !== "stopped"));
    setActivity(a);
    setShares(sh);
  }, [token]);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  const runSearch = useCallback(async (query: string) => {
    if (!query.trim() || !token) return;
    setSearching(true);
    try {
      const r = await apiFetch<{ devices: AllSearchResult[] }>(
        `/api/v1/files/search-all?q=${encodeURIComponent(query)}`, token,
      );
      setAllResults(r.devices.filter((d) => d.results.length > 0 || d.status === "online"));
    } finally {
      setSearching(false);
    }
  }, [token]);

  // sidebar ⌘K search lands here as ?q=
  const qParam = params.get("q");
  useEffect(() => {
    if (qParam) { setQ(qParam); runSearch(qParam); }
  }, [qParam, runSearch]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const firstName = (email ?? "there").split("@")[0];
  const online = devices.filter((d) => d.status === "online");
  const activeSyncs = syncs.filter((s) => s.state === "active");
  const today = new Date().toDateString();
  const todayActivity = activity.filter((a) => new Date(a.created_at).toDateString() === today);
  const ongoingTransfers = transfers.filter((t) => t.status === "active").length;
  const folderCards = [
    ...shares.owned.map((s) => ({ s, mine: true })),
    ...shares.granted.map((s) => ({ s, mine: false })),
  ].slice(0, 8);
  const resultCount = allResults?.reduce((n, d) => n + d.results.length, 0) ?? 0;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[1.6rem] font-semibold leading-tight tracking-[-0.02em]">
            {greeting}, {firstName}
          </h1>
          <p className="mt-1.5 text-sm text-[var(--color-text-dim)]">
            Here&apos;s what&apos;s happening across your connected computers.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/sync" className="btn btn-ghost"><FolderSync size={14} /> New sync</Link>
          <Link href="/permissions" className="btn btn-primary"><Share2 size={14} /> Share a folder</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard tone="purple" icon={<Monitor size={18} />} value={online.length}
          label="Devices online" hint={`${devices.length} total`} />
        <StatCard tone="green" icon={<RefreshCw size={18} />} value={activeSyncs.length}
          label="Active syncs" hint={syncs.length > activeSyncs.length ? `${syncs.length - activeSyncs.length} other` : undefined} />
        <StatCard tone="blue" icon={<ArrowLeftRight size={18} />} value={ongoingTransfers}
          label="Ongoing transfers" />
        <StatCard tone="amber" icon={<ActivityIcon size={18} />} value={todayActivity.length}
          label="Activities today" />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); runSearch(q); }}
        className="input mt-4 flex items-center gap-3 !rounded-2xl !p-2 !pl-4">
        <Search size={16} className="shrink-0 text-[var(--color-text-faint)]" />
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search files across all your computers…"
          className="flex-1 bg-transparent text-sm outline-none" />
        <button className="btn btn-primary !rounded-xl" disabled={searching || !q.trim()}>
          {searching ? <Spinner size={14} /> : <Search size={14} />} Search
        </button>
      </form>

      {allResults && (
        <div className="card pop-in mt-4 overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              Results <span className="pill">{resultCount} across {allResults.length} computer{allResults.length === 1 ? "" : "s"}</span>
            </div>
            <button onClick={() => setAllResults(null)} className="icon-btn !h-7 !w-7" aria-label="Clear">
              <X size={13} />
            </button>
          </div>
          {allResults.length === 0 && (
            <div className="p-8 text-center text-sm text-[var(--color-text-dim)]">
              No matches — files only appear in search after a folder is shared on that computer.
            </div>
          )}
          {allResults.map((d) => (
            <div key={d.device_id}>
              <div className="flex items-center gap-2 bg-[rgba(0,0,0,0.2)] px-4 py-2 text-xs font-semibold text-[var(--color-text-dim)]">
                <StatusDot status={d.status} /> {d.device_name}
                <span className="pill ml-1">{d.results.length}</span>
              </div>
              {d.results.slice(0, 10).map((f) => (
                <a key={f.path}
                  href={`/files?device=${d.device_id}&path=${encodeURIComponent(f.path)}`}
                  className="flex items-center gap-3 border-t border-[var(--color-border)] px-4 py-2.5 text-sm transition-colors hover:bg-[rgba(255,255,255,0.02)]">
                  <FileIcon name={f.name} isDir={f.is_dir} size={22} />
                  <span className="min-w-0 flex-1 truncate font-medium">{f.name}</span>
                  <span className="hidden max-w-[40%] truncate text-xs text-[var(--color-text-faint)] md:block">{f.path}</span>
                  <span className="w-16 text-right text-xs text-[var(--color-text-dim)]">{formatBytes(f.size)}</span>
                  <ArrowRight size={13} className="text-[var(--color-text-faint)]" />
                </a>
              ))}
            </div>
          ))}
        </div>
      )}

      {folderCards.length > 0 && (
        <div className="mt-6">
          <CardHeader title="Shared folders" count={shares.owned.length + shares.granted.length}
            action={<Link href="/permissions" className="text-xs font-medium text-[var(--color-accent)] hover:underline">Manage</Link>} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {folderCards.map(({ s, mine }) => (
              <Link key={(s.grant_id ?? "") + s.id}
                href={`/files?device=${s.device_id}&path=${encodeURIComponent(s.root_path)}`}
                className="card card-hover group overflow-hidden">
                <div className="flex flex-col items-center px-4 pb-4 pt-6">
                  <div className="transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:scale-[1.03]">
                    <FolderArt size={72} tone={mine ? "orange" : "purple"} />
                  </div>
                  <div className="mt-3 w-full truncate text-center text-sm font-semibold">
                    {s.label || basename(s.root_path)}
                  </div>
                  <span className="pill mt-1.5">{s.device_name || "your computer"}</span>
                </div>
                <div className="space-y-1.5 border-t border-[var(--color-border)] bg-[rgba(0,0,0,0.15)] px-4 py-3 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-[var(--color-text-faint)]">Owner</span>
                    <span className="truncate pl-2 text-[var(--color-text-dim)]">{mine ? "You" : s.owner_email ?? "Colleague"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--color-text-faint)]">Access</span>
                    <span className="text-[var(--color-text-dim)]">
                      {mine ? "Full" : (s.permissions ?? 0) & 256 ? "Manager" : (s.permissions ?? 0) & 4 ? "Editor" : "Viewer"}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="card p-5">
          <CardHeader title="Connected computers" count={devices.length}
            action={<Link href="/devices" className="text-xs font-medium text-[var(--color-accent)] hover:underline">View all</Link>} />
          <div className="space-y-2">
            {devices.slice(0, 5).map((d) => (
              <Link key={d.id} href="/devices"
                className="well flex items-center gap-3 px-3 py-2.5 transition-colors hover:border-[var(--color-border-strong)]">
                <IconTile tone={d.status === "online" ? "green" : "purple"} size={36}>
                  <Monitor size={16} />
                </IconTile>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{d.name}</div>
                  <div className="text-xs text-[var(--color-text-faint)]">
                    {d.status === "online" ? `${d.platform} · online now` : `Last seen ${timeAgo(d.last_seen_at)}`}
                  </div>
                </div>
                <span className={`badge ${d.status === "online" ? "badge-green" : "badge-gray"}`}>
                  <StatusDot status={d.status} /> {d.status}
                </span>
              </Link>
            ))}
            {devices.length === 0 && (
              <div className="well dots p-6 text-center text-xs text-[var(--color-text-dim)]">
                No computers yet —{" "}
                <Link href="/devices" className="font-medium text-[var(--color-accent)]">connect your first one</Link>
              </div>
            )}
          </div>
        </div>

        <div className="card p-5">
          <CardHeader title="Recent activity"
            action={<Link href="/activity" className="text-xs font-medium text-[var(--color-accent)] hover:underline">View all</Link>} />
          <div className="relative">
            {activity.length > 0 && (
              <span className="absolute bottom-3 left-[13px] top-3 w-px bg-[var(--color-border)]" />
            )}
            <div className="space-y-3.5">
              {activity.slice(0, 6).map((a) => (
                <div key={a.id} className="relative flex items-start gap-3 text-xs">
                  <span className="relative z-10 flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-accent)]">
                    {ACTION_ICONS[a.action] ?? <ActivityIcon size={13} />}
                  </span>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium text-[var(--color-text)]">{ACTION_LABELS[a.action] ?? a.action}</span>
                      <span className="shrink-0 text-[var(--color-text-faint)]">{timeAgo(a.created_at)}</span>
                    </div>
                    {a.target && (
                      <div className="mt-0.5 truncate text-[var(--color-text-dim)]">{basename(a.target)}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {activity.length === 0 && (
              <p className="py-6 text-center text-xs text-[var(--color-text-dim)]">
                Nothing yet — activity appears as you use NetSync.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  return (
    <Suspense fallback={<div className="py-16 text-center"><Spinner /></div>}>
      <DashboardInner />
    </Suspense>
  );
}
