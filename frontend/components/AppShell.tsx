"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Bot, ChevronDown, FolderGit2, LayoutDashboard, MonitorSmartphone,
  History, RefreshCw, Settings, ShieldCheck, LogOut, Boxes,
} from "lucide-react";
import { apiFetch, API_URL } from "@/lib/api";
import { useAuth, type Auth } from "@/lib/useAuth";
import { initials } from "@/lib/format";
import { StatusDot } from "@/components/ui";
import { TransferProvider } from "@/components/TransferCenter";
import type { Device } from "@/types";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/assistant", label: "AI Assistant", icon: Bot },
  { href: "/files", label: "Files", icon: FolderGit2 },
  { href: "/sync", label: "Synchronization", icon: RefreshCw },
  { href: "/devices", label: "Devices", icon: MonitorSmartphone },
  { href: "/permissions", label: "Permissions", icon: ShieldCheck },
  { href: "/activity", label: "Activity", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

function BackendBadge() {
  const [state, setState] = useState<"checking" | "online" | "down">("checking");
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const r = await fetch(`${API_URL}/health`, { cache: "no-store" });
        if (alive) setState(r.ok ? "online" : "down");
      } catch {
        if (alive) setState("down");
      }
    };
    check();
    const t = setInterval(check, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const cfg = {
    checking: { label: "Backend: connecting…", cls: "badge-amber", dot: "bg-[var(--color-warn)]" },
    online: { label: "Backend: connected", cls: "badge-green", dot: "bg-[var(--color-online)]" },
    down: { label: "Backend: unreachable", cls: "badge-red", dot: "bg-[var(--color-danger)]" },
  }[state];
  return (
    <span className={`badge ${cfg.cls}`} title={`${API_URL}\n${state === "down" ? "The page will retry every 30s — the backend may be waking up." : ""}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${cfg.dot} pulse-dot`} />
      {cfg.label}
    </span>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const auth = useAuth();
  const [devices, setDevices] = useState<Device[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!auth.token) return;
    let alive = true;
    const load = () =>
      apiFetch<Device[]>("/api/v1/devices", auth.token!)
        .then((d) => alive && setDevices(d.filter((x) => !x.revoked_at)))
        .catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [auth.token]);

  useEffect(() => {
    const close = (e: MouseEvent) =>
      !menuRef.current?.contains(e.target as Node) && setMenuOpen(false);
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);

  const online = devices.filter((d) => d.status === "online").length;

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-[rgba(20,20,28,0.75)] backdrop-blur">
        <Link href="/dashboard" className="flex items-center gap-2.5 px-5 py-5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#8b5cf6] to-[#5f32d6]">
            <Boxes size={18} className="text-white" />
          </span>
          <div className="leading-tight">
            <div className="font-semibold">NetSync AI</div>
            <div className="text-[10px] text-[var(--color-text-dim)]">Distributed File Automation</div>
          </div>
        </Link>

        <nav className="space-y-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link key={href} href={href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-[rgba(139,92,246,0.15)] font-medium text-[var(--color-accent)]"
                    : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
                }`}>
                <Icon size={16} /> {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-6 px-5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Connected computers{devices.length > 0 ? ` (${devices.length})` : ""}
        </div>
        <div className="mt-1 space-y-0.5 px-3">
          {devices.map((d) => (
            <div key={d.id} className="flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-sm">
              <StatusDot status={d.status} />
              <span className="truncate">{d.name}</span>
            </div>
          ))}
          {devices.length === 0 && (
            <div className="px-3 py-1.5 text-xs text-[var(--color-text-dim)]">
              No computers yet —{" "}
              <Link href="/devices" className="text-[var(--color-accent)]">add one</Link>
            </div>
          )}
        </div>

        <div className="mt-auto p-4">
          <div className="card p-3 text-xs text-[var(--color-text-dim)]">
            <span className="font-medium text-[var(--color-text)]">{online}</span> online ·{" "}
            <span>{devices.length - online}</span> offline
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[rgba(12,12,18,0.85)] px-6 backdrop-blur">
          <div className="flex items-center gap-3 text-sm text-[var(--color-text-dim)]">
            <BackendBadge />
            {NAV.find((n) => n.href === pathname)?.label ?? "NetSync AI"}
          </div>
          <div className="relative" ref={menuRef}>
            <button onClick={() => setMenuOpen((o) => !o)}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-[var(--color-surface-2)]">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-primary)] text-xs font-bold text-white">
                {initials(auth.email ?? "U")}
              </span>
              <span className="max-w-[160px] truncate text-sm">{auth.email ?? ""}</span>
              <ChevronDown size={14} className="text-[var(--color-text-dim)]" />
            </button>
            {menuOpen && (
              <div className="card fade-up absolute right-0 top-full mt-1 w-44 p-1.5">
                <Link href="/settings" onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-[var(--color-surface-2)]">
                  <Settings size={14} /> Settings
                </Link>
                <button onClick={auth.signOut}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-[var(--color-danger)] hover:bg-[var(--color-surface-2)]">
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <TransferProvider>
      <AppShell>{children}</AppShell>
    </TransferProvider>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  if (!auth.configured) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="card max-w-md p-6 text-sm text-[var(--color-text-dim)]">
          Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and
          NEXT_PUBLIC_SUPABASE_ANON_KEY.
        </div>
      </div>
    );
  }
  if (!auth.ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)]" />
      </div>
    );
  }
  return <Shell>{children}</Shell>;
}

export type { Auth };
