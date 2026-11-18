"use client";

import { useEffect, useState } from "react";
import {
  Check, Download, Globe2, Info, LogOut, MonitorCog, ShieldCheck, User,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { PageHeader, Spinner } from "@/components/ui";
import { initials } from "@/lib/format";

interface Prefs { display_name: string; discoverable: boolean; email?: string; user_id?: string }

const SECTIONS = [
  { key: "general", label: "General", icon: User },
  { key: "agent", label: "Desktop App", icon: MonitorCog },
  { key: "security", label: "Security", icon: ShieldCheck },
  { key: "about", label: "About", icon: Info },
];

import { agentDownload, isMac } from "@/lib/download";

const AGENT_DOWNLOAD_URL = process.env.NEXT_PUBLIC_AGENT_DOWNLOAD_URL ?? "";

export default function SettingsPage() {
  const auth = useAuth();
  const { token, signOut } = auth;
  const [section, setSection] = useState("general");
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [name, setName] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    apiFetch<Prefs>("/api/v1/me/preferences", token)
      .then((p) => { setPrefs(p); setName(p.display_name ?? ""); })
      .catch(() => setPrefs({ display_name: "", discoverable: true }));
  }, [token]);

  async function save(patch: Partial<Prefs>) {
    if (!token) return;
    setBusy(true); setSaved(false); setError(null);
    try {
      const p = await apiFetch<Prefs>("/api/v1/me/preferences", token, {
        method: "PUT", body: JSON.stringify(patch),
      });
      setPrefs((old) => ({ ...(old ?? { discoverable: true }), ...p, email: p.email ?? old?.email }));
      setSaved(true); setTimeout(() => setSaved(false), 1500);
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle="Configure your account, agent, and application preferences." />
      <div className="grid gap-5 md:grid-cols-[200px_1fr]">
        {/* section nav */}
        <div className="space-y-1">
          {SECTIONS.map((s) => (
            <button key={s.key} onClick={() => setSection(s.key)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${
                section === s.key
                  ? "bg-[rgba(139,92,246,0.15)] font-medium text-[var(--color-accent)]"
                  : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-2)]"
              }`}>
              <s.icon size={15} /> {s.label}
            </button>
          ))}
        </div>

        <div className="max-w-xl">
          {section === "general" && (
            <>
              <div className="card p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold">
                  <User size={15} className="text-[var(--color-accent)]" /> Account
                </h2>
                <div className="mt-4 flex items-center gap-3">
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-primary)] font-bold text-white">
                    {initials(prefs?.email ?? auth.email ?? "U")}
                  </span>
                  <div>
                    <div className="font-medium">{prefs?.display_name || name || "—"}</div>
                    <div className="text-xs text-[var(--color-text-dim)]">{prefs?.email ?? auth.email}</div>
                  </div>
                </div>
                <div className="mt-4">
                  <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Display name</label>
                  <input className="input w-full" value={name}
                    onChange={(e) => setName(e.target.value)} placeholder="Shown to colleagues" />
                </div>
                <div className="mt-3">
                  <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Your user ID</label>
                  <code className="block truncate rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text-dim)]">
                    {prefs?.user_id ?? ""}
                  </code>
                  <p className="mt-1 text-[11px] text-[var(--color-text-dim)]">
                    Give this to a colleague if they can't find you by email.
                  </p>
                </div>
              </div>

              <div className="card mt-4 p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold">
                  <Globe2 size={15} className="text-[var(--color-accent)]" /> Sharing
                </h2>
                <div className="mt-3 flex items-start justify-between gap-4">
                  <div className="text-sm">
                    <div className="font-medium">Let colleagues find me by @handle</div>
                    <p className="mt-0.5 text-xs leading-relaxed text-[var(--color-text-dim)]">
                      Grants by exact email always work — this only controls
                      whether people can discover you by handle.
                    </p>
                  </div>
                  <button
                    onClick={() => save({ discoverable: !(prefs?.discoverable ?? true) })}
                    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                      prefs?.discoverable ? "bg-[var(--color-primary)]" : "bg-[var(--color-surface-3)]"
                    }`}>
                    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                      prefs?.discoverable ? "left-[22px]" : "left-0.5"
                    }`} />
                  </button>
                </div>
                {error && <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>}
                <div className="mt-4">
                  <button className="btn btn-primary" disabled={busy}
                    onClick={() => save({ display_name: name })}>
                    {busy ? <Spinner size={14} /> : saved ? <Check size={14} /> : null} Save changes
                  </button>
                </div>
              </div>
            </>
          )}

          {section === "agent" && (
            <div className="card p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <MonitorCog size={15} className="text-[var(--color-accent)]" /> Desktop app
              </h2>
              <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-dim)]">
                The NetSync AI app keeps this computer connected in the
                background{isMac() ? "" : " — it starts with Windows, lives in the system tray,"}
                {" "}and handles file transfers and sync for folders you share.
              </p>
              {AGENT_DOWNLOAD_URL && (
                <a href={agentDownload().url} className="btn btn-primary mt-4">
                  <Download size={14} /> {agentDownload().label}
                </a>
              )}
              <ul className="mt-4 space-y-2 text-xs text-[var(--color-text-dim)]">
                <li>• {isMac() ? "Run it once — it stays connected while it's running" : "Starts automatically when you sign in"}</li>
                <li>• Pair from Devices → Add this computer — no commands needed</li>
                <li>• Your shared folders and access levels are managed on the Devices page</li>
                <li>• {isMac() ? "On first launch, right-click → Open to pass Gatekeeper" : "Remove it from Settings → Apps → NetSync AI"}</li>
              </ul>
            </div>
          )}

          {section === "security" && (
            <div className="card p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <ShieldCheck size={15} className="text-[var(--color-accent)]" /> Security
              </h2>
              <ul className="mt-3 space-y-2 text-xs text-[var(--color-text-dim)]">
                <li>• Devices connect with one-time pairing codes (10-minute expiry)</li>
                <li>• Only credential hashes are stored — never your files or passwords</li>
                <li>• File contents never touch cloud storage — transfers go agent-to-browser</li>
                <li>• Revoke any computer instantly from the Devices page</li>
              </ul>
              <div className="mt-5 border-t border-[var(--color-border)] pt-4">
                <button className="btn btn-danger" onClick={signOut}>
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            </div>
          )}

          {section === "about" && (
            <div className="card p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Info size={15} className="text-[var(--color-accent)]" /> About NetSync AI
              </h2>
              <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-dim)]">
                AI-driven multi-agent distributed file management and real-time
                synchronization. Agents run on your computers; the cloud only
                coordinates — your files never leave your machines unencrypted
                to us.
              </p>
              <div className="mt-3 text-xs text-[var(--color-text-dim)]">
                Agent v0.2.0 · Dashboard, backend, and agent are open source.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
