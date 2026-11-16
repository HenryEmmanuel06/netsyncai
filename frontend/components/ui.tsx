"use client";

import { useEffect, useRef } from "react";
import { FileText, FileImage, FileVideo, FileAudio, FileArchive,
         FileCode, FileSpreadsheet, File, Folder } from "lucide-react";

export function PageHeader({ title, subtitle, actions }: {
  title: string; subtitle?: string; actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-[var(--color-text-dim)]">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ icon, label, value, hint, tone = "purple" }: {
  icon: React.ReactNode; label: string; value: React.ReactNode;
  hint?: string; tone?: "purple" | "green" | "blue" | "amber";
}) {
  const tones = {
    purple: "text-[var(--color-accent)] bg-[rgba(139,92,246,0.14)]",
    green: "text-[var(--color-online)] bg-[rgba(52,211,153,0.12)]",
    blue: "text-[#7db4f8] bg-[rgba(96,165,250,0.12)]",
    amber: "text-[var(--color-warn)] bg-[rgba(251,191,36,0.12)]",
  };
  return (
    <div className="card card-hover flex items-center gap-4 p-5">
      <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${tones[tone]}`}>
        {icon}
      </span>
      <div>
        <div className="text-2xl font-semibold leading-none">{value}</div>
        <div className="mt-1.5 text-xs text-[var(--color-text-dim)]">
          {label}{hint ? ` · ${hint}` : ""}
        </div>
      </div>
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]"
      style={{ width: size, height: size }}
    />
  );
}

export function EmptyState({ icon, title, hint, action }: {
  icon: React.ReactNode; title: string; hint?: string; action?: React.ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--color-surface-2)] text-[var(--color-text-dim)]">
        {icon}
      </span>
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-sm text-xs text-[var(--color-text-dim)]">{hint}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: {
  title: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div ref={ref}
        className={`card fade-up max-h-[85vh] w-full overflow-y-auto p-5 ${wide ? "max-w-2xl" : "max-w-md"}`}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose}
            className="rounded p-1 text-[var(--color-text-dim)] hover:text-[var(--color-text)]">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ConfirmDialog({ title, body, confirmLabel, danger, busy, onConfirm, onCancel }: {
  title: string; body: string; confirmLabel?: string; danger?: boolean;
  busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="text-sm text-[var(--color-text-dim)]">{body}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
          disabled={busy} onClick={onConfirm}>
          {busy ? <Spinner size={14} /> : null} {confirmLabel ?? "Confirm"}
        </button>
      </div>
    </Modal>
  );
}

const EXT_COLORS: Record<string, string> = {
  pdf: "text-red-400",
  doc: "text-blue-400", docx: "text-blue-400",
  xls: "text-green-400", xlsx: "text-green-400", csv: "text-green-400",
  png: "text-purple-300", jpg: "text-purple-300", jpeg: "text-purple-300", gif: "text-purple-300", svg: "text-purple-300",
  mp4: "text-pink-400", mkv: "text-pink-400", mov: "text-pink-400",
  mp3: "text-amber-300", wav: "text-amber-300",
  zip: "text-yellow-500", rar: "text-yellow-500", "7z": "text-yellow-500",
  py: "text-yellow-300", ts: "text-blue-300", tsx: "text-blue-300", js: "text-yellow-300", jsx: "text-yellow-300",
};

export function FileIcon({ name, isDir, size = 18 }: { name: string; isDir?: boolean; size?: number }) {
  if (isDir) return <Folder size={size} className="shrink-0 text-[var(--color-warn)]" />;
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const color = EXT_COLORS[ext] ?? "text-[var(--color-text-dim)]";
  if (["png", "jpg", "jpeg", "gif", "svg"].includes(ext)) return <FileImage size={size} className={`shrink-0 ${color}`} />;
  if (["mp4", "mkv", "mov"].includes(ext)) return <FileVideo size={size} className={`shrink-0 ${color}`} />;
  if (["mp3", "wav"].includes(ext)) return <FileAudio size={size} className={`shrink-0 ${color}`} />;
  if (["zip", "rar", "7z"].includes(ext)) return <FileArchive size={size} className={`shrink-0 ${color}`} />;
  if (["xls", "xlsx", "csv"].includes(ext)) return <FileSpreadsheet size={size} className={`shrink-0 ${color}`} />;
  if (["py", "ts", "tsx", "js", "jsx", "html", "css", "json"].includes(ext)) return <FileCode size={size} className={`shrink-0 ${color}`} />;
  if (ext) return <FileText size={size} className={`shrink-0 ${color}`} />;
  return <File size={size} className="shrink-0 text-[var(--color-text-dim)]" />;
}

export const PERM_BITS = [
  { bit: 1, label: "browse" },
  { bit: 2, label: "download" },
  { bit: 4, label: "upload" },
  { bit: 8, label: "rename" },
  { bit: 16, label: "edit" },
  { bit: 32, label: "move" },
  { bit: 64, label: "delete" },
  { bit: 128, label: "new folder" },
  { bit: 256, label: "sync" },
  { bit: 512, label: "manage sync" },
];

export function PermBadges({ bits }: { bits: number }) {
  return (
    <span className="flex flex-wrap gap-1">
      {PERM_BITS.filter((p) => bits & p.bit).map((p) => (
        <span key={p.bit} className="rounded bg-[var(--color-surface-3)] px-1.5 py-0.5 text-[10px]">
          {p.label}
        </span>
      ))}
      {bits === 0 && <span className="text-xs text-[var(--color-text-dim)]">none</span>}
    </span>
  );
}

export function StatusDot({ status }: { status: string }) {
  const online = status === "online";
  return (
    <span className={`inline-block h-2 w-2 rounded-full ${online ? "bg-[var(--color-online)] pulse-dot" : "bg-[var(--color-offline)]"}`} />
  );
}
