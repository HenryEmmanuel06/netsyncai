"use client";

import { useEffect, useState } from "react";
import {
  ArrowDownToLine, ArrowUpToLine, Check, Clock, RefreshCw, Trash2,
} from "lucide-react";
import { useTransfers, type Transfer } from "@/components/TransferCenter";
import { useAuth } from "@/lib/useAuth";
import { EmptyState, FileIcon, PageHeader } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { Device, SyncSession } from "@/types";

const TABS = [
  { key: "ongoing", label: "Ongoing", filter: (t: Transfer) => t.status === "active" },
  { key: "completed", label: "Completed", filter: (t: Transfer) => t.status === "done" },
  { key: "failed", label: "Failed / Cancelled", filter: (t: Transfer) => t.status === "error" || t.status === "cancelled" },
];

interface AgentTransfer {
  id: string; name: string; size: number; received: number;
  direction: "in" | "out"; rel_path: string; dest: string;
  session_id: string; done: boolean; ok: boolean;
}

interface LiveSide {
  device_id: string; root: string; online: boolean;
  transfers?: AgentTransfer[];
}

interface SyncRow {
  key: string;
  t: AgentTransfer;
  sessionName: string;
  deviceName: string;
}

export default function TransfersPage() {
  const { token } = useAuth();
  const { transfers, cancel, dismiss, clearFinished } = useTransfers();
  const [tab, setTab] = useState("ongoing");
  const [syncRows, setSyncRows] = useState<SyncRow[]>([]);
  const activeTab = TABS.find((t) => t.key === tab)!;
  const rows = [...transfers].reverse().filter(activeTab.filter);
  const counts = Object.fromEntries(TABS.map((t) => [t.key, transfers.filter(t.filter).length]));

  // agent-reported computer-to-computer sync transfers
  useEffect(() => {
    if (!token) return;
    let dead = false;
    const tick = async () => {
      try {
        const [sessions, devices] = await Promise.all([
          apiFetch<SyncSession[]>("/api/v1/sync", token),
          apiFetch<Device[]>("/api/v1/devices", token),
        ]);
        const names = new Map(devices.map((d) => [d.id, d.name]));
        const lives = await Promise.all(
          sessions.filter((s) => s.state === "active").map((s) =>
            apiFetch<{ sides: LiveSide[] }>(`/api/v1/sync/${s.id}/live`, token)
              .then((l) => ({ s, l })).catch(() => null)),
        );
        if (dead) return;
        // both agents report the same transfer_id — dedupe, preferring the
        // receiver's row since it carries the local drop location
        const byId = new Map<string, SyncRow>();
        for (const item of lives) {
          if (!item) continue;
          for (const side of item.l.sides) {
            for (const t of side.transfers ?? []) {
              if (t.session_id !== item.s.id || !t.name) continue;
              const existing = byId.get(t.id);
              if (existing && existing.t.direction !== "out") continue;
              byId.set(t.id, {
                key: t.id, t,
                sessionName: item.s.name,
                deviceName: names.get(side.device_id) ?? "colleague's PC",
              });
            }
          }
        }
        setSyncRows([...byId.values()]);
      } catch { /* backend unreachable — leave the last snapshot */ }
    };
    void tick();
    const iv = setInterval(tick, 4000);
    return () => { dead = true; clearInterval(iv); };
  }, [token]);

  const shownSync = syncRows.filter((r) =>
    activeTab.key === "ongoing" ? !r.t.done
      : activeTab.key === "completed" ? r.t.done && r.t.ok
      : r.t.done && !r.t.ok);
  const syncCounts = {
    ongoing: syncRows.filter((r) => !r.t.done).length,
    completed: syncRows.filter((r) => r.t.done && r.t.ok).length,
    failed: syncRows.filter((r) => r.t.done && !r.t.ok).length,
  } as Record<string, number>;

  return (
    <div>
      <PageHeader title="Transfers"
        subtitle="Downloads and uploads between your browser and connected computers."
        actions={
          <button className="btn btn-ghost" onClick={clearFinished}
            disabled={!transfers.some((t) => t.status !== "active")}>
            <Trash2 size={14} /> Clear finished
          </button>
        }
      />

      <div className="segmented mb-5">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`tab ${tab === t.key ? "tab-active" : ""}`}>
            {t.label} ({counts[t.key] + (syncCounts[t.key] ?? 0)})
          </button>
        ))}
      </div>

      {rows.length === 0 && shownSync.length === 0 ? (
        <EmptyState icon={<ArrowDownToLine size={20} />} title={`No ${activeTab.label.toLowerCase()} transfers`}
          hint="Downloads and uploads from the Files page, and files moving between synced computers, appear here." />
      ) : (
        <div className="card divide-y divide-[var(--color-border)]">
          {rows.map((t) => <Row key={t.id} t={t}
            onCancel={() => cancel(t.id)} onDismiss={() => dismiss(t.id)} />)}
          {shownSync.map((r) => <SyncTransferRow key={r.key} r={r} />)}
        </div>
      )}
    </div>
  );
}

function SyncTransferRow({ r }: { r: SyncRow }) {
  const { t } = r;
  const pct = t.size > 0 ? Math.min(100, Math.round((t.received / t.size) * 100)) : null;
  const incoming = t.direction !== "out";
  const Icon = incoming ? ArrowDownToLine : ArrowUpToLine;
  const active = !t.done;
  return (
    <div className="flex items-center gap-4 px-4 py-3.5">
      <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${
        active ? "bg-[rgba(139,92,246,0.14)] text-[var(--color-accent)]"
          : t.ok ? "bg-[rgba(52,211,153,0.12)] text-[var(--color-online)]"
          : "bg-[var(--color-surface-2)] text-[var(--color-text-dim)]"}`}>
        {active ? <Icon size={16} /> : t.ok ? <Check size={16} /> : <Clock size={16} />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <FileIcon name={t.name} size={14} />
          <span className="truncate text-sm font-medium">{t.name || t.rel_path}</span>
          <span className="badge badge-gray">
            {incoming ? `receiving on ${r.deviceName}` : `sending from ${r.deviceName}`}
          </span>
          <span className="badge badge-purple">sync</span>
        </div>
        <div className="mt-1.5 flex items-center gap-3">
          {active ? (
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
              <div className="h-full rounded-full bg-[var(--color-primary)] transition-all"
                style={{ width: `${pct ?? 15}%` }} />
            </div>
          ) : (
            <span className="text-xs text-[var(--color-text-dim)]">
              {t.ok ? `${formatBytes(t.received || t.size)} completed` : "transfer failed"}
            </span>
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 truncate text-[11px] text-[var(--color-text-faint)]">
          <RefreshCw size={10} className="shrink-0" />
          <span className="truncate">
            {t.dest ? `dropping to ${t.dest}` : t.rel_path || r.sessionName}
          </span>
        </div>
      </div>
      <div className="w-24 shrink-0 text-right text-xs text-[var(--color-text-dim)]">
        {active ? (pct !== null ? `${pct}%` : formatBytes(t.received))
                : formatBytes(t.received || t.size)}
      </div>
    </div>
  );
}

function Row({ t, onCancel, onDismiss }: { t: Transfer; onCancel: () => void; onDismiss: () => void }) {
  const pct = t.size > 0 ? Math.round((t.received / t.size) * 100) : null;
  const Icon = t.direction === "down" ? ArrowDownToLine : ArrowUpToLine;
  return (
    <div className="flex items-center gap-4 px-4 py-3.5">
      <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${
        t.status === "active" ? "bg-[rgba(139,92,246,0.14)] text-[var(--color-accent)]"
          : t.status === "done" ? "bg-[rgba(52,211,153,0.12)] text-[var(--color-online)]"
          : "bg-[var(--color-surface-2)] text-[var(--color-text-dim)]"}`}>
        {t.status === "done" ? <Check size={16} /> : t.status === "active" ? <Icon size={16} /> : <Clock size={16} />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <FileIcon name={t.name} size={14} />
          <span className="truncate text-sm font-medium">{t.name}</span>
          <span className="badge badge-gray capitalize">{t.direction === "down" ? "download" : "upload"}</span>
        </div>
        <div className="mt-1.5 flex items-center gap-3">
          {t.status === "active" ? (
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
              <div className="h-full rounded-full bg-[var(--color-primary)] transition-all"
                style={{ width: `${pct ?? 15}%` }} />
            </div>
          ) : (
            <span className="text-xs text-[var(--color-text-dim)]">
              {t.status === "done" && `${formatBytes(t.received || t.size)} completed`}
              {t.status === "error" && (t.error ?? "transfer failed")}
              {t.status === "cancelled" && "cancelled"}
            </span>
          )}
        </div>
      </div>
      <div className="w-24 shrink-0 text-right text-xs text-[var(--color-text-dim)]">
        {t.status === "active" ? (pct !== null ? `${pct}%` : formatBytes(t.received)) : formatBytes(t.received || t.size)}
      </div>
      {t.status === "active" ? (
        <button className="btn btn-ghost !px-2.5 !py-1 text-xs" onClick={onCancel}>Cancel</button>
      ) : (
        <button className="btn btn-ghost !px-2.5 !py-1 text-xs" onClick={onDismiss}>Dismiss</button>
      )}
    </div>
  );
}
