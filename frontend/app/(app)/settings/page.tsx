"use client";

import { useEffect, useState } from "react";
import { Check, Globe2, LogOut, User } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { PageHeader, Spinner } from "@/components/ui";

interface Prefs { display_name: string; discoverable: boolean; email?: string; user_id?: string }

export default function SettingsPage() {
  const auth = useAuth();
  const { token, signOut } = auth;
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
    <div className="mx-auto max-w-xl">
      <PageHeader title="Settings" subtitle="Your account and sharing preferences." />

      <div className="card p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <User size={15} className="text-[var(--color-accent)]" /> Profile
        </h2>
        <div className="mt-3 space-y-3 text-sm">
          <div>
            <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Email</label>
            <input className="input w-full" value={prefs?.email ?? auth.email ?? ""} disabled />
          </div>
          <div>
            <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Display name</label>
            <input className="input w-full" value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Shown to colleagues" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Your user ID</label>
            <code className="block truncate rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text-dim)]">
              {prefs?.user_id ?? ""}
            </code>
            <p className="mt-1 text-[11px] text-[var(--color-text-dim)]">
              Give this to a colleague if they can't find you by email.
            </p>
          </div>
        </div>
      </div>

      <div className="card mt-4 p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Globe2 size={15} className="text-[var(--color-accent)]" /> Sharing
        </h2>
        <div className="mt-3 flex items-start justify-between gap-4">
          <div className="text-sm">
            <div className="font-medium">Let colleagues find me</div>
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--color-text-dim)]">
              When off, people can't look you up by email or @handle to grant
              you access to their folders — they'd need your user ID.
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
        <div className="mt-4 flex items-center gap-2">
          <button className="btn btn-primary" disabled={busy}
            onClick={() => save({ display_name: name })}>
            {busy ? <Spinner size={14} /> : saved ? <Check size={14} /> : null} Save
          </button>
        </div>
      </div>

      <div className="card mt-4 p-5">
        <button className="btn btn-danger" onClick={signOut}>
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </div>
  );
}
