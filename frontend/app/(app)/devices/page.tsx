"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import type { Device } from "@/types";
import { Plus } from "lucide-react";

const STATUS_COLOR: Record<Device["status"], string> = {
  online: "text-green-400",
  busy: "text-amber-400",
  invisible: "text-slate-400",
  offline: "text-red-400",
};

interface PairingCode {
  code: string;
  expires_at: string;
  expires_in_seconds: number;
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval>>(null);

  const refresh = useCallback(async (t: string) => {
    try {
      setDevices(await apiFetch<Device[]>("/api/v1/devices", t));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load devices");
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (!supabaseConfigured) {
        setError("Supabase not configured — see .env.example");
        return;
      }
      const supabase = getSupabaseBrowser();
      const { data } = await supabase!.auth.getSession();
      if (!data.session) {
        setError("Sign in to view your devices");
        return;
      }
      setToken(data.session.access_token);
      await refresh(data.session.access_token);
      timer.current = setInterval(
        () => refresh(data.session.access_token),
        5000,
      );
    })();
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [refresh]);

  async function createPairing(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !name.trim()) return;
    setBusy(true);
    try {
      setPairing(
        await apiFetch<PairingCode>("/api/v1/pairing", token, {
          method: "POST",
          body: JSON.stringify({ device_name: name.trim() }),
        }),
      );
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "pairing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Devices</h1>
      <p className="mt-1 text-sm text-[var(--color-text-dim)]">
        Computers registered to your account.
      </p>

      <form onSubmit={createPairing} className="card mt-6 flex gap-2 p-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Device name (e.g. Aje-Laptop)"
          className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]"
        />
        <button
          type="submit"
          disabled={busy || !token}
          className="flex items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          <Plus size={16} /> Pair device
        </button>
      </form>

      {pairing && (
        <div className="card mt-4 border-[var(--color-primary)] p-4">
          <div className="text-sm text-[var(--color-text-dim)]">
            Run this on the new device (valid {Math.round(pairing.expires_in_seconds / 60)} min, single use):
          </div>
          <code className="mt-2 block rounded bg-[var(--color-surface-2)] p-3 text-sm">
            netsync-agent pair {pairing.code}
          </code>
          <div className="mt-1 text-center text-2xl font-bold tracking-[0.3em] text-[var(--color-primary)]">
            {pairing.code}
          </div>
        </div>
      )}

      <div className="mt-6 space-y-2">
        {error && <div className="card p-4 text-sm text-[var(--color-text-dim)]">{error}</div>}
        {devices?.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            No devices yet. Generate a pairing code above, then run it in the
            desktop agent on the computer you want to connect.
          </div>
        )}
        {devices?.map((d) => (
          <div key={d.id} className="card flex items-center justify-between p-4">
            <div>
              <div className="font-medium">{d.name}</div>
              <div className="text-xs text-[var(--color-text-dim)]">
                {d.platform} · agent {d.agent_version ?? "—"}
                {d.revoked_at && " · revoked"}
              </div>
            </div>
            <span className={`text-sm capitalize ${STATUS_COLOR[d.status]}`}>
              ● {d.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
