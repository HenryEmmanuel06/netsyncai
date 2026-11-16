"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import type { Device, SharedFolder } from "@/types";
import { Share2, Trash2, UserPlus } from "lucide-react";

const PERM_BITS = [
  { bit: 1, label: "browse" },
  { bit: 2, label: "download" },
  { bit: 4, label: "upload" },
  { bit: 8, label: "rename" },
  { bit: 32, label: "move" },
  { bit: 64, label: "delete" },
  { bit: 128, label: "create folder" },
];

function PermBadges({ bits }: { bits: number }) {
  return (
    <span className="flex flex-wrap gap-1">
      {PERM_BITS.filter((p) => bits & p.bit).map((p) => (
        <span key={p.bit} className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 text-[10px]">
          {p.label}
        </span>
      ))}
    </span>
  );
}

export default function PermissionsPage() {
  const [token, setToken] = useState<string | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [owned, setOwned] = useState<SharedFolder[]>([]);
  const [granted, setGranted] = useState<SharedFolder[]>([]);
  const [grants, setGrants] = useState<Record<string, {id: string; subject_user_id: string; permissions_granted: number}[]>>({});
  const [deviceId, setDeviceId] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [label, setLabel] = useState("");
  const [grantTarget, setGrantTarget] = useState<SharedFolder | null>(null);
  const [subject, setSubject] = useState("");
  const [permBits, setPermBits] = useState<number>(3); // browse+download
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (t: string) => {
    const [devs, shares] = await Promise.all([
      apiFetch<Device[]>("/api/v1/devices", t),
      apiFetch<{ owned: SharedFolder[]; granted: SharedFolder[] }>(
        "/api/v1/sharing", t,
      ),
    ]);
    setDevices(devs.filter((d) => !d.revoked_at));
    setOwned(shares.owned);
    setGranted(shares.granted);
  }, []);

  useEffect(() => {
    (async () => {
      if (!supabaseConfigured) return;
      const sb = getSupabaseBrowser();
      const { data } = await sb!.auth.getSession();
      if (!data.session) return;
      setToken(data.session.access_token);
      await load(data.session.access_token);
    })();
  }, [load]);

  async function createShare(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/v1/sharing", token!, {
        method: "POST",
        body: JSON.stringify({ device_id: deviceId, root_path: rootPath, label }),
      });
      setRootPath(""); setLabel("");
      await load(token!);
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    }
  }

  async function addGrant(e: React.FormEvent) {
    e.preventDefault();
    if (!grantTarget) return;
    setError(null);
    try {
      await apiFetch(`/api/v1/sharing/${grantTarget.id}/grants`, token!, {
        method: "POST",
        body: JSON.stringify({ subject, permissions: permBits }),
      });
      setSubject("");
      setGrantTarget(null);
      await load(token!);
    } catch (err) {
      setError(err instanceof Error ? err.message : "grant failed");
    }
  }

  async function removeShare(id: string) {
    if (!window.confirm("Remove this share? Grants are deleted.")) return;
    await apiFetch(`/api/v1/sharing/${id}`, token!, { method: "DELETE" });
    await load(token!);
  }

  async function showGrants(share: SharedFolder) {
    const g = await apiFetch<{id: string; subject_user_id: string; permissions_granted: number}[]>(
      `/api/v1/sharing/${share.id}/grants`, token!,
    );
    setGrants((prev) => ({ ...prev, [share.id]: g }));
  }

  async function revokeGrant(shareId: string, grantId: string) {
    await apiFetch(`/api/v1/sharing/${shareId}/grants/${grantId}`, token!, {
      method: "DELETE",
    });
    await load(token!);
    const share = owned.find((s) => s.id === shareId);
    if (share) await showGrants(share);
  }

  function toggleBit(bit: number) {
    setPermBits((b) => (b & bit ? b & ~bit : b | bit));
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Permissions</h1>
      <p className="mt-1 text-sm text-[var(--color-text-dim)]">
        Share folders from your devices with other NetSync users. The folder
        must be indexed on the agent (<code>--access read</code> or higher).
      </p>

      <form onSubmit={createShare} className="card mt-6 space-y-3 p-4">
        <h2 className="text-sm font-medium">Share a folder</h2>
        <div className="grid grid-cols-2 gap-3">
          <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} required
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
            <option value="">Device…</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <input value={label} onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (e.g. Project files)"
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm" />
          <input value={rootPath} onChange={(e) => setRootPath(e.target.value)} required
            placeholder="Root path on that device (e.g. C:\shared\docs)"
            className="col-span-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm" />
        </div>
        <button className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium">
          <Share2 size={14} className="mr-1 inline" /> Create share
        </button>
      </form>

      {error && <div className="card mt-4 p-3 text-sm text-red-400">{error}</div>}

      <h2 className="mt-8 text-lg font-medium">Your shared folders</h2>
      <div className="mt-3 space-y-3">
        {owned.map((s) => (
          <div key={s.id} className="card p-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="font-medium">{s.label || s.root_path}</div>
                <div className="mt-1 text-xs text-[var(--color-text-dim)]">
                  {s.device_name} · {s.root_path}
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setGrantTarget(s)}
                  className="rounded border border-[var(--color-border)] px-2 py-1 text-xs">
                  <UserPlus size={12} className="mr-1 inline" /> Grant
                </button>
                <button onClick={() => showGrants(s)}
                  className="rounded border border-[var(--color-border)] px-2 py-1 text-xs">Grants</button>
                <button onClick={() => removeShare(s.id)}
                  className="rounded border border-[var(--color-border)] px-2 py-1 text-xs text-red-400">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>

            {grantTarget?.id === s.id && (
              <form onSubmit={addGrant} className="mt-3 border-t border-[var(--color-border)] pt-3">
                <div className="flex flex-wrap gap-2">
                  <input value={subject} onChange={(e) => setSubject(e.target.value)} required
                    placeholder="user UUID, email, or @handle"
                    className="flex-1 rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-xs" />
                  <button className="rounded bg-[var(--color-primary)] px-3 py-1.5 text-xs font-medium">Add</button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {PERM_BITS.map((p) => (
                    <label key={p.bit} className="flex items-center gap-1 text-xs">
                      <input type="checkbox" checked={!!(permBits & p.bit)}
                        onChange={() => toggleBit(p.bit)} />
                      {p.label}
                    </label>
                  ))}
                </div>
              </form>
            )}

            {grants[s.id] && (
              <div className="mt-3 space-y-1 border-t border-[var(--color-border)] pt-3">
                {grants[s.id].length === 0 && (
                  <div className="text-xs text-[var(--color-text-dim)]">No grants yet.</div>
                )}
                {grants[s.id].map((g) => (
                  <div key={g.id} className="flex items-center justify-between text-xs">
                    <span className="font-mono">{g.subject_user_id.slice(0, 8)}…</span>
                    <span className="flex items-center gap-2">
                      <PermBadges bits={g.permissions_granted} />
                      <button onClick={() => revokeGrant(s.id, g.id)} className="text-red-400">revoke</button>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {owned.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">No shares yet.</div>
        )}
      </div>

      <h2 className="mt-8 text-lg font-medium">Shared with you</h2>
      <div className="mt-3 space-y-3">
        {granted.map((s) => (
          <div key={s.grant_id ?? s.id} className="card flex items-center justify-between p-4">
            <div>
              <div className="font-medium">{s.label || s.root_path}</div>
              <div className="mt-1 text-xs text-[var(--color-text-dim)]">
                {s.device_name} · {s.root_path}
              </div>
            </div>
            <PermBadges bits={s.permissions ?? 0} />
          </div>
        ))}
        {granted.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            Nothing shared with you yet.
          </div>
        )}
      </div>
    </div>
  );
}
