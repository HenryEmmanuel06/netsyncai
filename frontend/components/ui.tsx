"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";

export interface DropdownOption {
  value: string;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
  group?: string;
  disabled?: boolean;
}

/** Styled replacement for <select> — the native popup can't be themed. */
export function Dropdown({ value, options, onChange, placeholder = "Choose…", className = "", align = "left" }: {
  value: string; options: DropdownOption[]; onChange: (v: string) => void;
  placeholder?: string; className?: string; align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  // fixed coords from the trigger rect — the menu must escape
  // overflow-hidden ancestors (tables, modals) that would clip it
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number; up?: boolean } | null>(null);
  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) { setPos(null); return; }
    const measure = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      const MENU_MAX = 288 + 8;                       // max-h-72 + margin
      const below = window.innerHeight - r.bottom;
      const up = below < MENU_MAX && r.top > below;
      const left = align === "right"
        ? { right: window.innerWidth - r.right }
        : { left: r.left };
      setPos({ top: up ? r.top - 6 : r.bottom + 6, up, ...left });
    };
    measure();
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    // reposition on scroll/resize — closing here raced the focus-scroll
    // that fires when the button gets clicked, hiding the menu instantly
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [open, align]);

  const groups: { name?: string; items: DropdownOption[] }[] = [];
  for (const o of options) {
    const last = groups[groups.length - 1];
    if (last && last.name === o.group) last.items.push(o);
    else groups.push({ name: o.group, items: [o] });
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button ref={btnRef} type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}
        className={`input flex w-full items-center gap-2 text-left ${open ? "!border-[rgba(139,92,246,0.7)] !shadow-[0_0_0_3px_rgba(139,92,246,0.16)]" : ""}`}>
        {current?.icon}
        <span className={`min-w-0 flex-1 truncate ${current ? "" : "text-[var(--color-text-faint)]"}`}>
          {current?.label ?? placeholder}
        </span>
        {current?.hint && <span className="shrink-0 text-[11px] text-[var(--color-text-faint)]">{current.hint}</span>}
        <ChevronDown size={14} className={`shrink-0 text-[var(--color-text-dim)] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && pos && (
        <div className="fixed z-[60]" style={{
          top: pos.top, left: pos.left, right: pos.right,
          minWidth: btnRef.current?.offsetWidth,
          ...(pos.up ? { transform: "translateY(-100%)" } : {}),
        }}>
        <div role="listbox"
          className="card pop-in max-h-72 min-w-full overflow-y-auto p-1.5 !shadow-[0_16px_40px_-8px_rgba(0,0,0,0.7)]"
          style={{ width: "max-content", maxWidth: 340 }}>
          {groups.map((g, gi) => (
            <div key={gi} className={gi > 0 ? "mt-1 border-t border-[var(--color-border)] pt-1" : ""}>
              {g.name && <div className="section-label px-2.5 pb-1 pt-1.5">{g.name}</div>}
              {g.items.map((o) => {
                const active = o.value === value;
                return (
                  <button key={o.value} type="button" role="option" aria-selected={active}
                    disabled={o.disabled}
                    onClick={() => { onChange(o.value); setOpen(false); }}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors disabled:opacity-40 ${
                      active ? "bg-[rgba(139,92,246,0.12)] text-[var(--color-text)]" : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
                    }`}>
                    {o.icon}
                    <span className="min-w-0 flex-1 truncate">{o.label}</span>
                    {o.hint && <span className="shrink-0 text-[11px] text-[var(--color-text-faint)]">{o.hint}</span>}
                    <Check size={13} className={`shrink-0 text-[var(--color-accent)] ${active ? "" : "invisible"}`} />
                  </button>
                );
              })}
            </div>
          ))}
          {options.length === 0 && (
            <div className="px-3 py-4 text-center text-xs text-[var(--color-text-faint)]">Nothing to choose yet</div>
          )}
        </div>
        </div>
      )}
    </div>
  );
}

/** Barebones expandable picker — plain divs that overlay the content
 *  above the trigger (bottom-full), so nothing — clipping, stacking or
 *  fixed positioning — can hide the options. Use where Dropdown's
 *  fixed-position menu has rendered unreliably. */
export function InlinePick({ value, placeholder, options, onPick,
  empty = "Nothing here", className = "w-48" }: {
  value: string; placeholder: string; options: DropdownOption[];
  onPick: (v: string) => void; empty?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cur = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="input flex w-full items-center gap-2 !py-1.5 text-left text-xs">
        <span className={`min-w-0 flex-1 truncate ${cur ? "" : "text-[var(--color-text-faint)]"}`}>
          {cur?.label ?? placeholder}
        </span>
        <ChevronDown size={13} className={`shrink-0 text-[var(--color-text-dim)] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-20 mb-1 max-h-48 min-w-full overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] shadow-[0_16px_40px_-8px_rgba(0,0,0,0.7)]">
          {options.length === 0 ? (
            <div className="px-3 py-2.5 text-[11px] text-[var(--color-warn)]">{empty}</div>
          ) : options.map((o) => (
            <button key={o.value} type="button" disabled={o.disabled}
              onClick={() => { onPick(o.value); setOpen(false); }}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--color-surface-3)] disabled:opacity-40 ${
                o.value === value ? "text-[var(--color-accent)]" : "text-[var(--color-text-dim)]"
              }`}>
              {o.icon}
              <span className="min-w-0 flex-1 truncate">{o.label}</span>
              {o.hint && <span className="shrink-0 text-[10px] text-[var(--color-text-faint)]">{o.hint}</span>}
              <Check size={12} className={`shrink-0 text-[var(--color-accent)] ${o.value === value ? "" : "invisible"}`} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: {
  title: string; subtitle?: string; actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[1.6rem] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
        {subtitle && <p className="mt-1.5 text-sm text-[var(--color-text-dim)]">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const TONES = {
  purple: { fg: "#b197fc", bg: "rgba(139,92,246,0.14)", ring: "rgba(139,92,246,0.28)" },
  green: { fg: "#34d399", bg: "rgba(52,211,153,0.12)", ring: "rgba(52,211,153,0.26)" },
  blue: { fg: "#8ec0fb", bg: "rgba(96,165,250,0.12)", ring: "rgba(96,165,250,0.26)" },
  amber: { fg: "#fbbf24", bg: "rgba(251,191,36,0.12)", ring: "rgba(251,191,36,0.26)" },
} as const;

export function IconTile({ children, tone = "purple", size = 40 }: {
  children: React.ReactNode; tone?: keyof typeof TONES; size?: number;
}) {
  const t = TONES[tone];
  return (
    <span className="flex shrink-0 items-center justify-center rounded-xl"
      style={{
        width: size, height: size, color: t.fg, background: t.bg,
        boxShadow: `inset 0 0 0 1px ${t.ring}, inset 0 1px 0 rgba(255,255,255,0.08)`,
      }}>
      {children}
    </span>
  );
}

export function StatCard({ icon, label, value, hint, tone = "purple" }: {
  icon: React.ReactNode; label: string; value: React.ReactNode;
  hint?: string; tone?: keyof typeof TONES;
}) {
  return (
    <div className="card card-hover p-4">
      <div className="flex items-start justify-between">
        <IconTile tone={tone}>{icon}</IconTile>
        {hint && <span className="pill">{hint}</span>}
      </div>
      <div className="mt-4 text-[1.75rem] font-semibold leading-none tracking-tight">{value}</div>
      <div className="mt-1.5 text-xs text-[var(--color-text-dim)]">{label}</div>
    </div>
  );
}

/** Card section header — title + optional count/action row. */
export function CardHeader({ title, count, action }: {
  title: string; count?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {count !== undefined && <span className="pill">{count}</span>}
      </div>
      {action}
    </div>
  );
}

/** Illustrated folder (the orange "Fillo" folder with papers peeking out). */
export function FolderArt({ size = 64, tone = "orange" }: {
  size?: number; tone?: "orange" | "purple" | "blue";
}) {
  const id = useId().replace(/:/g, "");
  const c = {
    orange: ["#ffb35c", "#ff8a2a", "#e8741a"],
    purple: ["#b69bff", "#8b5cf6", "#6d3fe0"],
    blue: ["#8ec5ff", "#4f9bff", "#2f7ae6"],
  }[tone];
  return (
    <svg width={size} height={size * 0.82} viewBox="0 0 80 66" fill="none" aria-hidden>
      <defs>
        <linearGradient id={`f-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={c[0]} />
          <stop offset="1" stopColor={c[1]} />
        </linearGradient>
      </defs>
      <path d="M6 10a6 6 0 0 1 6-6h17l6 6h33a6 6 0 0 1 6 6v40a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6V10Z" fill={c[2]} />
      <rect x="16" y="11" width="44" height="34" rx="3" fill="#f4f1ec" transform="rotate(-6 16 11)" />
      <rect x="21" y="9" width="42" height="34" rx="3" fill="#ffffff" />
      <rect x="27" y="16" width="22" height="2.6" rx="1.3" fill="#d8d3cc" />
      <rect x="27" y="22" width="30" height="2.6" rx="1.3" fill="#e6e1da" />
      <path d="M4 26a6 6 0 0 1 6-6h60a6 6 0 0 1 6 6l-2 30a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6L4 26Z" fill={`url(#f-${id})`} />
      <path d="M10 21h60a6 6 0 0 1 5.6 3.8" stroke="rgba(255,255,255,0.45)" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
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

export function EmptyState({ icon, title, hint, action, art }: {
  icon?: React.ReactNode; title: string; hint?: string; action?: React.ReactNode;
  art?: React.ReactNode;
}) {
  return (
    <div className="card dots flex flex-col items-center gap-2 px-6 py-14 text-center">
      {art ?? (
        <span className="mb-1 flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-dim)] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          {icon}
        </span>
      )}
      <div className="mt-1 text-sm font-semibold">{title}</div>
      {hint && <div className="max-w-sm text-xs leading-relaxed text-[var(--color-text-dim)]">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Modal({ title, subtitle, icon, onClose, children, footer, wide }: {
  title: string; subtitle?: string; icon?: React.ReactNode;
  onClose: () => void; children: React.ReactNode;
  footer?: React.ReactNode; wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div ref={ref}
        className={`card pop-in flex max-h-[88vh] w-full flex-col overflow-hidden !rounded-2xl !shadow-[0_24px_60px_-12px_rgba(0,0,0,0.7)] ${wide ? "max-w-3xl" : "max-w-md"}`}>
        <div className="flex items-start gap-3 border-b border-[var(--color-border)] px-5 py-4">
          {icon && <IconTile size={36}>{icon}</IconTile>}
          <div className="min-w-0 flex-1">
            <h2 className="text-[0.95rem] font-semibold leading-tight">{title}</h2>
            {subtitle && <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-dim)]">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="icon-btn !h-8 !w-8" aria-label="Close">
            <X size={15} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] bg-[rgba(0,0,0,0.18)] px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: {
  label: string; hint?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div>
      <label className="field-label">{label}</label>
      {children}
      {hint && <p className="mt-1.5 text-[11px] leading-snug text-[var(--color-text-faint)]">{hint}</p>}
    </div>
  );
}

export function ConfirmDialog({ title, body, confirmLabel, danger, busy, onConfirm, onCancel }: {
  title: string; body: string; confirmLabel?: string; danger?: boolean;
  busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
            disabled={busy} onClick={onConfirm}>
            {busy ? <Spinner size={14} /> : null} {confirmLabel ?? "Confirm"}
          </button>
        </>
      }>
      <p className="text-sm leading-relaxed text-[var(--color-text-dim)]">{body}</p>
    </Modal>
  );
}

// label colour per extension group — drives the tag on the page icon
const EXT_GROUPS: { exts: string[]; color: string }[] = [
  { exts: ["pdf"], color: "#ef4444" },
  { exts: ["doc", "docx", "odt", "rtf", "txt", "md"], color: "#3b82f6" },
  { exts: ["xls", "xlsx", "csv", "ods"], color: "#16a34a" },
  { exts: ["ppt", "pptx", "odp", "key"], color: "#f97316" },
  { exts: ["png", "jpg", "jpeg", "gif", "webp", "heic", "bmp"], color: "#a855f7" },
  { exts: ["svg", "fig", "psd", "ai", "sketch"], color: "#d946ef" },
  { exts: ["mp4", "mkv", "mov", "avi", "webm"], color: "#ec4899" },
  { exts: ["mp3", "wav", "flac", "m4a", "ogg"], color: "#eab308" },
  { exts: ["zip", "rar", "7z", "tar", "gz"], color: "#ca8a04" },
  { exts: ["py", "ts", "tsx", "js", "jsx", "html", "css", "json", "java", "c", "cpp", "go", "rs"], color: "#0ea5e9" },
  { exts: ["exe", "msi", "dmg", "apk"], color: "#64748b" },
];

function extColor(ext: string): string {
  return EXT_GROUPS.find((g) => g.exts.includes(ext))?.color ?? "#71717a";
}

/** Page-shaped file icon with a coloured extension tag (".pdf", ".doc"…). */
export function FileIcon({ name, isDir, size = 18 }: { name: string; isDir?: boolean; size?: number }) {
  if (isDir) return <FolderArt size={size * 1.25} />;
  const ext = (name.includes(".") ? name.split(".").pop() : "")?.toLowerCase() ?? "";
  const color = extColor(ext);
  const label = ext.slice(0, 4);
  const w = size * 0.82;
  const h = size;
  return (
    <span className="relative inline-flex shrink-0" style={{ width: w + size * 0.18, height: h }} aria-hidden>
      <svg width={w} height={h} viewBox="0 0 24 30" fill="none">
        <path d="M3 2.5A2.5 2.5 0 0 1 5.5 0H16l8 8v19.5a2.5 2.5 0 0 1-2.5 2.5h-16A2.5 2.5 0 0 1 3 27.5v-25Z" fill="#f4f4f5" />
        <path d="M16 0v5.5A2.5 2.5 0 0 0 18.5 8H24L16 0Z" fill="#d4d4d8" />
      </svg>
      {label && size >= 16 && (
        <span className="absolute bottom-[12%] left-0 rounded-[3px] px-[3px] font-bold leading-none text-white shadow-sm"
          style={{ background: color, fontSize: Math.max(6, size * 0.27), paddingTop: 1.5, paddingBottom: 1.5 }}>
          .{label}
        </span>
      )}
    </span>
  );
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
        <span key={p.bit} className="pill !px-2 !py-0 !text-[10px]">
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
    <span className="relative inline-flex h-2 w-2 shrink-0">
      {online && <span className="absolute inset-0 animate-ping rounded-full bg-[var(--color-online)] opacity-40" />}
      <span className={`relative inline-block h-2 w-2 rounded-full ${online ? "bg-[var(--color-online)] shadow-[0_0_8px_rgba(52,211,153,0.7)]" : "bg-[var(--color-offline)]"}`} />
    </span>
  );
}
