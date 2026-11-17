"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeftRight, Bot, ChevronDown, FolderGit2, LayoutDashboard, MonitorSmartphone,
  History, RefreshCw, Settings, ShieldCheck, LogOut, Boxes, Search, HardDrive,
} from "lucide-react";
import { apiFetch, API_URL } from "@/lib/api";
import { useAuth, type Auth } from "@/lib/useAuth";
import { basename, formatBytes, initials } from "@/lib/format";
import { FolderArt, StatusDot } from "@/components/ui";
import { TransferProvider } from "@/components/TransferCenter";
import type { Device, SharedFolder } from "@/types";

type NavItem = { href: string; label: string; icon: typeof LayoutDashboard; badge?: "sync" | "access" };

const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Main menu",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/assistant", label: "AI Assistant", icon: Bot },
      { href: "/files", label: "Files", icon: FolderGit2 },
      { href: "/sync", label: "Synchronization", icon: RefreshCw, badge: "sync" },
      { href: "/transfers", label: "Transfers", icon: ArrowLeftRight },
    ],
  },
  {
    title: "Management",
    items: [
      { href: "/devices", label: "Devices", icon: MonitorSmartphone },
      { href: "/permissions", label: "Permissions", icon: ShieldCheck, badge: "access" },
      { href: "/activity", label: "Activity & logs", icon: History },
    ],
  },
];

const ALL_NAV = [...NAV_SECTIONS.flatMap((s) => s.items),
  { href: "/settings", label: "Settings", icon: Settings }];

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
    checking: { label: "Connecting…", cls: "badge-amber", dot: "bg-[var(--color-warn)]" },
    online: { label: "Connected", cls: "badge-green", dot: "bg-[var(--color-online)]" },
    down: { label: "Backend unreachable", cls: "badge-red", dot: "bg-[var(--color-danger)]" },
  }[state];
  return (
    <span className={`badge ${cfg.cls}`} title={`${API_URL}\n${state === "down" ? "The page will retry every 30s — the backend may be waking up." : ""}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${cfg.dot} pulse-dot`} />
      {cfg.label}
    </span>
  );
}

function StorageCard({ device, token }: { device: Device; token: string }) {
  const [drive, setDrive] = useState<{ drive: string; total: number; free: number } | null>(null);
  useEffect(() => {
    apiFetch<{ drives: { drive: string; total: number; free: number }[] }>(
      `/api/v1/devices/${device.id}/stats`, token,
    ).then((s) => setDrive(s.drives[0] ?? null)).catch(() => {});
  }, [device.id, token]);
  if (!drive) return null;
  const used = drive.total - drive.free;
  const usedPct = Math.round((used / drive.total) * 100);
  return (
    <div className="card p-3.5">
      <div className="flex items-center gap-2">
        <HardDrive size={14} className="text-[var(--color-text-dim)]" />
        <span className="text-[13px] font-semibold">Storage</span>
        <span className="ml-auto truncate text-[11px] text-[var(--color-text-faint)]">{device.name} · {drive.drive}</span>
      </div>
      <p className="mt-0.5 text-[11px] text-[var(--color-text-faint)]">
        {usedPct > 90 ? "Running low — free up space" : "Local disk on your computer"}
      </p>
      <div className="mt-3 flex justify-between text-[11px] text-[var(--color-text-dim)]">
        <span>{formatBytes(used)} of {formatBytes(drive.total)}</span>
        <span className="font-medium text-[var(--color-text)]">{usedPct}%</span>
      </div>
      <div className="progress mt-1.5"><span style={{ width: `${usedPct}%` }} /></div>
    </div>
  );
}

function NavLink({ item, active, count }: { item: NavItem; active: boolean; count?: number }) {
  const Icon = item.icon;
  return (
    <Link href={item.href}
      className={`group relative flex items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-[13px] transition-colors ${
        active
          ? "bg-[var(--color-surface-2)] font-medium text-[var(--color-text)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_0_0_1px_var(--color-border)]"
          : "text-[var(--color-text-dim)] hover:bg-[rgba(255,255,255,0.03)] hover:text-[var(--color-text)]"
      }`}>
      <Icon size={15} className={active ? "text-[var(--color-accent)]" : ""} />
      <span className="truncate">{item.label}</span>
      {!!count && (
        <span className="ml-auto flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--color-primary)] px-1.5 text-[10px] font-bold text-white">
          {count}
        </span>
      )}
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuth();
  const [devices, setDevices] = useState<Device[]>([]);
  const [shared, setShared] = useState<SharedFolder[]>([]);
  const [counts, setCounts] = useState<{ sync: number; access: number }>({ sync: 0, access: 0 });
  const [menuOpen, setMenuOpen] = useState(false);
  const [q, setQ] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!auth.token) return;
    let alive = true;
    const token = auth.token;
    const load = async () => {
      const [d, sh, syncReq, accessReq] = await Promise.all([
        apiFetch<Device[]>("/api/v1/devices", token).catch(() => null),
        apiFetch<{ granted: SharedFolder[] }>("/api/v1/sharing", token).catch(() => null),
        apiFetch<{ requests: unknown[] }>("/api/v1/sync/requests", token).catch(() => null),
        apiFetch<{ incoming: { status: string }[] }>("/api/v1/sharing/requests", token).catch(() => null),
      ]);
      if (!alive) return;
      if (d) setDevices(d.filter((x) => !x.revoked_at));
      if (sh) setShared(sh.granted ?? []);
      setCounts({
        sync: syncReq?.requests.length ?? 0,
        access: (accessReq?.incoming ?? []).filter((r) => r.status === "pending").length,
      });
    };
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [auth.token]);

  useEffect(() => {
    const close = (e: MouseEvent) =>
      !menuRef.current?.contains(e.target as Node) && setMenuOpen(false);
    window.addEventListener("mousedown", close);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    router.push(`/dashboard?q=${encodeURIComponent(q.trim())}`);
    searchRef.current?.blur();
  }

  const firstOnline = devices.find((d) => d.status === "online");
  const current = ALL_NAV.find((n) => n.href === pathname);
  const CurrentIcon = current?.icon ?? Boxes;

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-[244px] shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-sidebar)]">
        <Link href="/dashboard" className="flex items-center gap-2.5 px-4 pb-4 pt-5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#a07bff] via-[#8b5cf6] to-[#ff8a5c] shadow-[inset_0_1px_0_rgba(255,255,255,0.35),0_4px_14px_-4px_rgba(139,92,246,0.7)]">
            <Boxes size={17} className="text-white" />
          </span>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">NetSync AI</div>
            <div className="text-[10px] text-[var(--color-text-faint)]">Distributed file automation</div>
          </div>
        </Link>

        <form onSubmit={submitSearch} className="px-3">
          <label className="input flex cursor-text items-center gap-2 !rounded-lg !py-[7px] !text-[13px]">
            <Search size={14} className="shrink-0 text-[var(--color-text-faint)]" />
            <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search files…"
              className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[var(--color-text-faint)]" />
            <kbd>⌘K</kbd>
          </label>
        </form>

        <nav className="mt-2 flex-1 overflow-y-auto px-3 pb-3">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="mt-4">
              <div className="section-label mb-1.5 px-2.5">{section.title}</div>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink key={item.href} item={item} active={pathname === item.href}
                    count={item.badge ? counts[item.badge] : undefined} />
                ))}
              </div>
            </div>
          ))}

          {shared.length > 0 && (
            <div className="mt-5">
              <div className="section-label mb-1.5 px-2.5">Shared with me</div>
              <div className="space-y-0.5">
                {shared.slice(0, 6).map((s) => (
                  <Link key={s.grant_id ?? s.id}
                    href={`/files?device=${s.device_id}&path=${encodeURIComponent(s.root_path)}`}
                    className="flex items-center gap-2.5 rounded-lg px-2.5 py-[6px] text-[13px] text-[var(--color-text-dim)] transition-colors hover:bg-[rgba(255,255,255,0.03)] hover:text-[var(--color-text)]">
                    <FolderArt size={16} tone="purple" />
                    <span className="truncate">{s.label || basename(s.root_path)}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="mt-5">
            <div className="section-label mb-1.5 flex items-center justify-between px-2.5">
              <span>Computers</span>
              {devices.length > 0 && <span className="normal-case tracking-normal">{devices.length}</span>}
            </div>
            <div className="space-y-0.5">
              {devices.map((d) => (
                <Link key={d.id} href="/devices"
                  className="flex items-center gap-2.5 rounded-lg px-2.5 py-[6px] text-[13px] text-[var(--color-text-dim)] transition-colors hover:bg-[rgba(255,255,255,0.03)] hover:text-[var(--color-text)]">
                  <StatusDot status={d.status} />
                  <span className="truncate">{d.name}</span>
                  <span className="ml-auto text-[10px] text-[var(--color-text-faint)]">
                    {d.status === "online" ? "online" : "offline"}
                  </span>
                </Link>
              ))}
              {devices.length === 0 && (
                <Link href="/devices" className="block px-2.5 py-1.5 text-xs text-[var(--color-accent)]">
                  + Connect a computer
                </Link>
              )}
            </div>
          </div>
        </nav>

        <div className="space-y-2 border-t border-[var(--color-border)] p-3">
          {auth.token && firstOnline && <StorageCard device={firstOnline} token={auth.token} />}
          <NavLink item={{ href: "/settings", label: "Settings", icon: Settings }}
            active={pathname === "/settings"} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="z-20 flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[rgba(17,17,19,0.8)] px-6 backdrop-blur-xl">
          <div className="flex items-center gap-2.5 text-sm">
            <CurrentIcon size={16} className="text-[var(--color-text-dim)]" />
            <span className="font-medium">{current?.label ?? "NetSync AI"}</span>
          </div>
          <div className="flex items-center gap-3">
            <BackendBadge />
            <div className="relative" ref={menuRef}>
              <button onClick={() => setMenuOpen((o) => !o)}
                className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] py-1 pl-1 pr-3 transition-colors hover:border-[var(--color-border-strong)]">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[#a07bff] to-[#7c4dff] text-[11px] font-bold text-white">
                  {initials(auth.email ?? "U")}
                </span>
                <span className="max-w-[160px] truncate text-[13px]">{auth.email?.split("@")[0] ?? ""}</span>
                <ChevronDown size={13} className="text-[var(--color-text-dim)]" />
              </button>
              {menuOpen && (
                <div className="card pop-in absolute right-0 top-full mt-2 w-56 p-1.5">
                  <div className="truncate px-2.5 pb-2 pt-1.5 text-xs text-[var(--color-text-faint)]">{auth.email}</div>
                  <Link href="/settings" onClick={() => setMenuOpen(false)} className="menu-item">
                    <Settings size={14} /> Settings
                  </Link>
                  <button onClick={auth.signOut} className="menu-item !text-[var(--color-danger)]">
                    <LogOut size={14} /> Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] p-6 lg:p-8">{children}</div>
        </main>
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
