"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import type { Device } from "@/types";

const STATUS_COLOR: Record<Device["status"], string> = {
  online: "text-green-400",
  busy: "text-amber-400",
  invisible: "text-slate-400",
  offline: "text-red-400",
};

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      try {
        setDevices(
          await apiFetch<Device[]>("/api/v1/devices", data.session.access_token),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load devices");
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Devices</h1>
      <p className="mt-1 text-sm text-[var(--color-text-dim)]">
        Computers registered to your account. Pairing arrives in Phase 2.
      </p>
      <div className="mt-6 space-y-2">
        {error && <div className="card p-4 text-sm text-[var(--color-text-dim)]">{error}</div>}
        {devices?.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            No devices yet. Install the desktop agent and pair it with a code.
          </div>
        )}
        {devices?.map((d) => (
          <div key={d.id} className="card flex items-center justify-between p-4">
            <div>
              <div className="font-medium">{d.name}</div>
              <div className="text-xs text-[var(--color-text-dim)]">
                {d.platform} · agent {d.agent_version ?? "—"}
              </div>
            </div>
            <span className={`text-sm capitalize ${STATUS_COLOR[d.status]}`}>
              {d.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
