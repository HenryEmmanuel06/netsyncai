"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import type { Device, SyncSession } from "@/types";

export default function SyncPage() {
  const [token, setToken] = useState<string | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [sessions, setSessions] = useState<SyncSession[]>([]);
  const [aDev, setADev] = useState("");
  const [aPath, setAPath] = useState("");
  const [bDev, setBDev] = useState("");
  const [bPath, setBPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (t: string) => {
    const [devs, syncs] = await Promise.all([
      apiFetch<Device[]>("/api/v1/devices", t),
      apiFetch<SyncSession[]>("/api/v1/sync", t),
    ]);
    setDevices(devs.filter((d) => !d.revoked_at));
    setSessions(syncs);
  }, []);

  useEffect(() => {
    (async () => {
      if (!supabaseConfigured) return;
      const sb = getSupabaseBrowser();
      const { data } = await sb!.auth.getSession();
      if (!data.session) return;
      setToken(data.session.access_token);
      await load(data.session.access_token);
      const id = setInterval(() => load(data.session.access_token), 5000);
      return () => clearInterval(id);
    })();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const s = await apiFetch<SyncSession>("/api/v1/sync", token!, {
        method: "POST",
        body: JSON.stringify({
          a_device_id: aDev, a_path: aPath,
          b_device_id: bDev, b_path: bPath, mode: "live",
        }),
      });
      if (s.state === "error") setError(`sync failed to start: ${(s as {error?: string}).error ?? "agent refused"}`);
      await load(token!);
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    } finally {
      setBusy(false);
    }
  }

  async function action(id: string, a: string) {
    await apiFetch(`/api/v1/sync/${id}/${a}`, token!, { method: "POST" });
    await load(token!);
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Synchronization</h1>
      <p className="mt-1 text-sm text-[var(--color-text-dim)]">
        Bidirectional folder sync between two of your devices. Both folders must
        be indexed on their agents with <code>--access readwrite</code>.
      </p>

      <form onSubmit={create} className="card mt-6 space-y-3 p-4">
        <div className="grid grid-cols-2 gap-3">
          <select value={aDev} onChange={(e) => setADev(e.target.value)} required
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
            <option value="">Device A…</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.status})</option>)}
          </select>
          <input value={aPath} onChange={(e) => setAPath(e.target.value)} required
            placeholder="Folder path on A (e.g. C:\sync\a)"
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm" />
          <select value={bDev} onChange={(e) => setBDev(e.target.value)} required
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
            <option value="">Device B…</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.status})</option>)}
          </select>
          <input value={bPath} onChange={(e) => setBPath(e.target.value)} required
            placeholder="Folder path on B (e.g. C:\sync\b)"
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm" />
        </div>
        <button disabled={busy || aDev === bDev}
          className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium disabled:opacity-50">
          {busy ? "Starting…" : "Start syncing"}
        </button>
        {aDev === bDev && aDev && (
          <p className="text-xs text-red-400">Pick two different devices.</p>
        )}
      </form>

      {error && <div className="card mt-4 p-3 text-sm text-red-400">{error}</div>}

      <div className="mt-6 space-y-3">
        {sessions.map((s) => (
          <div key={s.id} className="card p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{s.name}</div>
                <div className="mt-1 text-xs text-[var(--color-text-dim)]">
                  {s.participants.map((p) => p.root).join("  ⇄  ")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium ${
                  s.state === "active" ? "text-green-400"
                  : s.state === "paused" ? "text-yellow-400" : "text-red-400"
                }`}>{s.state}</span>
                {s.state === "active" && (
                  <button onClick={() => action(s.id, "pause")}
                    className="rounded border border-[var(--color-border)] px-2 py-1 text-xs">Pause</button>
                )}
                {s.state === "paused" && (
                  <button onClick={() => action(s.id, "resume")}
                    className="rounded border border-[var(--color-border)] px-2 py-1 text-xs">Resume</button>
                )}
                {s.state !== "stopped" && (
                  <button onClick={() => action(s.id, "stop")}
                    className="rounded border border-[var(--color-border)] px-2 py-1 text-xs text-red-400">Stop</button>
                )}
              </div>
            </div>
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            No sync sessions yet.
          </div>
        )}
      </div>
    </div>
  );
}
