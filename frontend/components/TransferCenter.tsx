"use client";

import {
  createContext, useCallback, useContext, useRef, useState,
} from "react";
import { ArrowDownToLine, ArrowUpToLine, Check, X } from "lucide-react";
import { FileIcon } from "@/components/ui";
import { formatBytes } from "@/lib/format";

export interface Transfer {
  id: number;
  name: string;
  size: number;                       // 0 → indeterminate
  received: number;
  direction: "down" | "up";
  status: "active" | "done" | "error" | "cancelled";
  error?: string;
}

interface Handle { id: number; signal: AbortSignal }

interface Ctx {
  transfers: Transfer[];
  begin: (name: string, size: number, direction: "down" | "up") => Handle;
  progress: (id: number, received: number) => void;
  finish: (id: number) => void;
  fail: (id: number, error?: string) => void;
  cancel: (id: number) => void;
  dismiss: (id: number) => void;
}

const TransferContext = createContext<Ctx | null>(null);

export function useTransfers(): Ctx {
  const ctx = useContext(TransferContext);
  if (!ctx) throw new Error("useTransfers outside TransferProvider");
  return ctx;
}

let nextId = 1;

export function TransferProvider({ children }: { children: React.ReactNode }) {
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const controllers = useRef(new Map<number, AbortController>());
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const update = useCallback((id: number, patch: Partial<Transfer>) => {
    setTransfers((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }, []);

  const dismiss = useCallback((id: number) => {
    controllers.current.delete(id);
    const tm = timers.current.get(id);
    if (tm) clearTimeout(tm);
    timers.current.delete(id);
    setTransfers((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const autoDismiss = useCallback((id: number) => {
    timers.current.set(id, setTimeout(() => dismiss(id), 8000));
  }, [dismiss]);

  const begin = useCallback((name: string, size: number, direction: "down" | "up"): Handle => {
    const id = nextId++;
    const controller = new AbortController();
    controllers.current.set(id, controller);
    setTransfers((ts) => [...ts, {
      id, name, size, direction, received: 0, status: "active",
    }]);
    return { id, signal: controller.signal };
  }, []);

  const progress = useCallback((id: number, received: number) => {
    update(id, { received });
  }, [update]);

  const finish = useCallback((id: number) => {
    controllers.current.delete(id);
    update(id, { status: "done" });
    autoDismiss(id);
  }, [update, autoDismiss]);

  const fail = useCallback((id: number, error?: string) => {
    controllers.current.delete(id);
    update(id, { status: "error", error });
    autoDismiss(id);
  }, [update, autoDismiss]);

  const cancel = useCallback((id: number) => {
    controllers.current.get(id)?.abort();
    controllers.current.delete(id);
    update(id, { status: "cancelled" });
    autoDismiss(id);
  }, [update, autoDismiss]);

  return (
    <TransferContext.Provider value={{ transfers, begin, progress, finish, fail, cancel, dismiss }}>
      {children}
      <TransferWidget transfers={transfers} onCancel={cancel} onDismiss={dismiss} />
    </TransferContext.Provider>
  );
}

function TransferWidget({ transfers, onCancel, onDismiss }: {
  transfers: Transfer[];
  onCancel: (id: number) => void;
  onDismiss: (id: number) => void;
}) {
  if (transfers.length === 0) return null;
  const active = transfers.filter((t) => t.status === "active").length;
  return (
    <div className="fixed bottom-4 right-4 z-50 w-80">
      <div className="card overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs font-semibold">
          <span>Transfers{active > 0 ? ` — ${active} in progress` : ""}</span>
          {active === 0 && (
            <button onClick={() => transfers.forEach((t) => onDismiss(t.id))}
              className="text-[var(--color-text-dim)] hover:text-[var(--color-text)]">Clear</button>
          )}
        </div>
        <div className="max-h-64 overflow-y-auto">
          {transfers.map((t) => <TransferRow key={t.id} t={t}
            onCancel={() => onCancel(t.id)} onDismiss={() => onDismiss(t.id)} />)}
        </div>
      </div>
    </div>
  );
}

function TransferRow({ t, onCancel, onDismiss }: {
  t: Transfer; onCancel: () => void; onDismiss: () => void;
}) {
  const pct = t.size > 0 ? Math.min(100, (t.received / t.size) * 100) : 0;
  const Icon = t.direction === "down" ? ArrowDownToLine : ArrowUpToLine;
  return (
    <div className="border-b border-[var(--color-border)] px-3 py-2.5 last:border-0">
      <div className="flex items-center gap-2">
        <FileIcon name={t.name} size={14} />
        <span className="min-w-0 flex-1 truncate text-xs font-medium">{t.name}</span>
        {t.status === "active" && (
          <span className="flex items-center gap-1 text-[10px] text-[var(--color-text-dim)]">
            <Icon size={11} className="pulse-dot" />
            {t.size > 0 ? `${formatBytes(t.received)} / ${formatBytes(t.size)}` : formatBytes(t.received)}
          </span>
        )}
        {t.status === "done" && <Check size={13} className="text-[var(--color-online)]" />}
        {t.status === "error" && <span className="text-[10px] text-[var(--color-danger)]">failed</span>}
        {t.status === "cancelled" && <span className="text-[10px] text-[var(--color-text-dim)]">cancelled</span>}
        <button
          className="ml-1 rounded p-0.5 text-[var(--color-text-dim)] hover:text-[var(--color-text)]"
          onClick={t.status === "active" ? onCancel : onDismiss}
          title={t.status === "active" ? "Cancel" : "Dismiss"}>
          <X size={12} />
        </button>
      </div>
      {t.status === "active" && (
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
          {t.size > 0 ? (
            <div className="h-full rounded-full bg-[var(--color-primary)] transition-all"
              style={{ width: `${pct}%` }} />
          ) : (
            <div className="h-full w-1/3 animate-pulse rounded-full bg-[var(--color-primary)]" />
          )}
        </div>
      )}
      {t.error && <div className="mt-1 truncate text-[10px] text-[var(--color-danger)]">{t.error}</div>}
    </div>
  );
}
