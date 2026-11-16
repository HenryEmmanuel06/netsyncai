"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bot, FolderGit2, MonitorCog, RefreshCw, ShieldCheck,
  ArrowLeftRight, History, Settings,
} from "lucide-react";

const NAV = [
  { href: "/assistant", label: "AI Assistant", icon: Bot },
  { href: "/files", label: "Network Files", icon: FolderGit2 },
  { href: "/sync", label: "Synchronization", icon: RefreshCw },
  { href: "/devices", label: "Devices", icon: MonitorCog },
  { href: "/permissions", label: "Permissions", icon: ShieldCheck },
  { href: "/transfers", label: "Transfers", icon: ArrowLeftRight },
  { href: "/activity", label: "Activity", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 border-r border-[var(--color-border)] p-3">
      <div className="mb-4 px-2 text-lg font-bold">
        Net<span className="text-[var(--color-primary)]">Sync</span> AI
      </div>
      <nav className="space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                active
                  ? "bg-[var(--color-surface-2)] text-[var(--color-primary)]"
                  : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-2)]"
              }`}
            >
              <Icon size={16} /> {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
