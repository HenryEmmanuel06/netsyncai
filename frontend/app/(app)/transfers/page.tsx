"use client";

import { useState } from "react";
import { ArrowDownToLine, ArrowUpToLine, Check, Clock, Trash2 } from "lucide-react";
import { useTransfers, type Transfer } from "@/components/TransferCenter";
import { EmptyState, FileIcon, PageHeader } from "@/components/ui";
import { formatBytes } from "@/lib/format";

const TABS = [
  { key: "ongoing", label: "Ongoing", filter: (t: Transfer) => t.status === "active" },
  { key: "completed", label: "Completed", filter: (t: Transfer) => t.status === "done" },
  { key: "failed", label: "Failed / Cancelled", filter: (t: Transfer) => t.status === "error" || t.status === "cancelled" },
];

export default function TransfersPage() {
  const { transfers, cancel, dismiss, clearFinished } = useTransfers();
  const [tab, setTab] = useState("ongoing");
  const activeTab = TABS.find((t) => t.key === tab)!;
  const rows = [...transfers].reverse().filter(activeTab.filter);
  const counts = Object.fromEntries(TABS.map((t) => [t.key, transfers.filter(t.filter).length]));

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
            {t.label} ({counts[t.key]})
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <EmptyState icon={<ArrowDownToLine size={20} />} title={`No ${activeTab.label.toLowerCase()} transfers`}
          hint="Downloads and uploads from the Files page appear here — they stay for this session." />
      ) : (
        <div className="card divide-y divide-[var(--color-border)]">
          {rows.map((t) => <Row key={t.id} t={t}
            onCancel={() => cancel(t.id)} onDismiss={() => dismiss(t.id)} />)}
        </div>
      )}
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
