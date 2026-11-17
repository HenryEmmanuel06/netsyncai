"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight, Check, Monitor, Pause, Play, Plus, RefreshCw, ServerCrash,
  Square, Users,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { ConfirmDialog, EmptyState, Modal, PageHeader, Spinner, StatusDot } from "@/components/ui";
import { basename, formatDate } from "@/lib/format";
import type { Device, SharedFolder, SharedFolderInfo, SyncSession } from "@/types";

interface LiveSync { applied_ops: number; pending_ops: number; sides: { device_id: string; online: boolean; paused: boolean }[] }

function LiveOps({ sessionId, token }: { sessionId: string; token: string }) {
  const [live, setLive] = useState<LiveSync | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => apiFetch<LiveSync>(`/api/v1/sync/${sessionId}/live`, token)
      .then((r) => alive && setLive(r)).catch(() => {});
    load();
    const t = setInterval(load, 10000);
    return () => { alive = false; clearInterval(t); };
  }, [sessionId, token]);
  if (!live) return null;
  const onlineSides = live.sides.filter((s) => s.online).length;
  return (
    <div className="mt-2 flex items-center gap-3 text-[11px] text-[var(--color-text-dim)]">
      <span>{live.applied_ops} ops applied</span>
      <span>{live.pending_ops} pending</span>
      <span>{onlineSides}/{live.sides.length} sides live</span>
      {live.sides.some((s) => s.paused) && <span className="badge badge-amber">paused on device</span>}
    </div>
  );
}

const STATE_STYLE: Record<string, string> = {
  active: "badge-green",
  paused: "badge-amber",
  error: "badge-red",
  pending: "badge-blue",
  stopped: "badge-gray",
};

export default function SyncPage() {
  const { token } = useAuth();
  const [sessions, setSessions] = useState<SyncSession[] | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [shares, setShares] = useState<SharedFolder[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [aDevice, setADevice] = useState("");
  const [aFolders, setAFolders] = useState<SharedFolderInfo[]>([]);
  const [aPath, setAPath] = useState("");
  const [bKind, setBKind] = useState<"mine" | "colleague">("mine");
  const [bDevice, setBDevice] = useState("");
  const [bFolders, setBFolders] = useState<SharedFolderInfo[]>([]);
  const [bPath, setBPath] = useState("");
  const [mode, setMode] = useState("live");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [colleagueEmail, setColleagueEmail] = useState("");
  const [stopTarget, setStopTarget] = useState<SyncSession | null>(null);
  const [tab, setTab] = useState<"active" | "paused" | "stopped">("active");
  const [requests, setRequests] = useState<(SyncSession & { my_device_name?: string; my_root?: string })[]>([]);

  const load = useCallback(async () => {
    if (!token) return;
    const [s, d, sh, req] = await Promise.all([
      apiFetch<SyncSession[]>("/api/v1/sync", token),
      apiFetch<Device[]>("/api/v1/devices", token),
      apiFetch<{ granted: SharedFolder[] }>("/api/v1/sharing", token).catch(() => ({ granted: [] })),
      apiFetch<{ requests: (SyncSession & { my_device_name?: string; my_root?: string })[] }>(
        "/api/v1/sync/requests", token).catch(() => ({ requests: [] })),
    ]);
    setSessions(s);
    setDevices(d.filter((x) => !x.revoked_at));
    setShares((sh.granted ?? []).filter((x) => (x.permissions ?? 0) & 256));
    setRequests(req.requests ?? []);
  }, [token]);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const id = bKind === "mine" ? bDevice : "";
    if (!id || !token) { setBFolders([]); return; }
    apiFetch<{ folders: SharedFolderInfo[] }>(`/api/v1/devices/${id}/folders`, token)
      .then((r) => setBFolders(r.folders.filter((f) => f.access === "readwrite")))
      .catch(() => setBFolders([]));
  }, [bDevice, bKind, token]);

  useEffect(() => {
    if (!aDevice || !token) { setAFolders([]); return; }
    apiFetch<{ folders: SharedFolderInfo[] }>(`/api/v1/devices/${aDevice}/folders`, token)
      .then((r) => setAFolders(r.folders.filter((f) => f.access === "readwrite")))
      .catch(() => setAFolders([]));
  }, [aDevice, token]);

  async function create() {
    const bDev = bKind === "mine" ? bDevice : shares.find((s) => `share:${s.id}` === bPath)?.device_id;
    const bRoot = bKind === "mine" ? bPath : shares.find((s) => `share:${s.id}` === bPath)?.root_path;
    if (!aDevice || !aPath || !bDev || !bRoot) return;
    setBusy(true); setError(null);
    try {
      await apiFetch("/api/v1/sync", token!, {
        method: "POST",
        body: JSON.stringify({
          a_device_id: aDevice, a_path: aPath,
          b_device_id: bDev, b_path: bRoot, mode,
        }),
      });
      setCreateOpen(false);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
    finally { setBusy(false); }
  }

  async function respondToRequest(id: string, accept: boolean) {
    try {
      await apiFetch(`/api/v1/sync/${id}/${accept ? "accept" : "decline"}`,
        token!, { method: "POST" });
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
  }

  async function action(s: SyncSession, act: "pause" | "resume" | "stop") {
    try {
      await apiFetch(`/api/v1/sync/${s.id}/${act}`, token!, { method: "POST" });
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
  }

  const deviceName = useMemo(() => {
    const m = new Map(devices.map((d) => [d.id, d.name]));
    return (id: string) => m.get(id) ?? "other computer";
  }, [devices]);

  const filteredShares = useMemo(() => {
    const q = colleagueEmail.trim().toLowerCase();
    if (!q) return shares;
    return shares.filter((s) =>
      (s.owner_email ?? "").toLowerCase().includes(q));
  }, [shares, colleagueEmail]);

  return (
    <div>
      <PageHeader
        title="Synchronization"
        subtitle="Keep folders identical across computers — yours or a colleague's."
        actions={
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> New sync
          </button>
        }
      />

      {error && <div className="card mb-4 px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div>}

      {/* incoming sync requests — the "popup" the other user sees */}
      {requests.map((r) => (
        <div key={r.id}
          className="card mb-4 flex flex-wrap items-center gap-3 border-[var(--color-primary)] bg-[rgba(139,92,246,0.07)] p-4">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[rgba(139,92,246,0.18)]">
            <RefreshCw size={18} className="text-[var(--color-accent)]" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold">Sync request</div>
            <div className="mt-0.5 text-xs text-[var(--color-text-dim)]">
              A colleague wants to sync <span className="font-medium text-[var(--color-text)]">{basename(r.name.split("↔")[0]?.trim() || r.name)}</span>
              {" "}with <span className="font-medium text-[var(--color-text)]">{basename(r.my_root ?? "")}</span> on {r.my_device_name}.
              Accepting starts syncing immediately — their content downloads to your PC.
            </div>
          </div>
          <button className="btn btn-primary" onClick={() => respondToRequest(r.id, true)}>
            <Check size={14} /> Accept
          </button>
          <button className="btn btn-ghost" onClick={() => respondToRequest(r.id, false)}>
            Decline
          </button>
        </div>
      ))}

      {sessions !== null && sessions.length > 0 && (
        <div className="mb-4 flex gap-1 rounded-lg bg-[var(--color-surface-2)] p-1 w-fit">
          {(["active", "paused", "stopped"] as const).map((k) => (
            <button key={k} className={`tab ${tab === k ? "tab-active" : ""}`}
              onClick={() => setTab(k)}>
              {k === "active" ? "Active Syncs" : k === "paused" ? "Paused" : "Stopped"} (
              {sessions.filter((s) =>
                k === "active" ? s.state === "active" || s.state === "pending" || s.state === "error"
                  : s.state === k).length})
            </button>
          ))}
        </div>
      )}

      {sessions === null ? (
        <div className="py-16 text-center"><Spinner /></div>
      ) : sessions.length === 0 ? (
        <EmptyState
          icon={<ArrowLeftRight size={20} />}
          title="No sync sessions yet"
          hint="Link two folders — changes on either side appear on the other within seconds."
          action={<button className="btn btn-primary" onClick={() => setCreateOpen(true)}>New sync</button>}
        />
      ) : (
        <div className="space-y-3">
          {sessions.filter((s) =>
            tab === "active" ? s.state === "active" || s.state === "pending" || s.state === "error"
              : s.state === tab).map((s) => (
            <div key={s.id} className="card card-hover p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{s.name || basename(s.participants[0]?.root ?? "Sync")}</span>
                    <span className={`badge ${s.state === "pending" ? "badge-amber" : STATE_STYLE[s.state] ?? "badge-gray"}`}>
                      {s.state === "pending" ? "waiting for acceptance" : s.state}
                    </span>
                    {s.mode === "review" && <span className="badge badge-blue">review</span>}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--color-text-dim)]">
                    {s.participants.map((p, i) => (
                      <span key={p.device_id} className="flex items-center gap-1.5">
                        {i > 0 && <ArrowLeftRight size={11} className="text-[var(--color-accent)]" />}
                        <Monitor size={12} /> {deviceName(p.device_id)} · {basename(p.root) || p.root}
                      </span>
                    ))}
                  </div>
                  {(s.state === "active" || s.state === "paused") && (
                    <LiveOps sessionId={s.id} token={token!} />
                  )}
                </div>
                <div className="flex gap-2">
                  {s.state === "active" && (
                    <button className="btn btn-ghost" onClick={() => action(s, "pause")}>
                      <Pause size={13} /> Pause
                    </button>
                  )}
                  {s.state === "paused" && (
                    <button className="btn btn-primary" onClick={() => action(s, "resume")}>
                      <Play size={13} /> Resume
                    </button>
                  )}
                  {s.state !== "stopped" && (
                    <button className="btn btn-danger" onClick={() => setStopTarget(s)}>
                      <Square size={12} /> Stop
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <Modal title="New sync" onClose={() => setCreateOpen(false)} wide>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] p-3">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-dim)]">
                Side A — your computer
              </div>
              <select className="input mb-2 w-full" value={aDevice}
                onChange={(e) => { setADevice(e.target.value); setAPath(""); }}>
                <option value="">Device…</option>
                {devices.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              <select className="input w-full" value={aPath} disabled={!aDevice}
                onChange={(e) => setAPath(e.target.value)}>
                <option value="">
                  {aDevice ? (aFolders.length ? "Folder (read & write)…" : "No read/write folders shared") : "Pick a device"}
                </option>
                {aFolders.map((f) => <option key={f.id} value={f.path}>{f.label || basename(f.path)}</option>)}
              </select>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] p-3">
              <div className="mb-2 flex gap-2 text-xs font-semibold uppercase tracking-wide">
                <button className={bKind === "mine" ? "text-[var(--color-accent)]" : "text-[var(--color-text-dim)]"}
                  onClick={() => { setBKind("mine"); setBPath(""); setBDevice(""); }}>My device</button>
                <button className={bKind === "colleague" ? "text-[var(--color-accent)]" : "text-[var(--color-text-dim)]"}
                  onClick={() => { setBKind("colleague"); setBPath(""); setBDevice(""); }}>
                  <Users size={11} className="inline" /> Colleague
                </button>
              </div>
              {bKind === "mine" ? (
                <>
                  <select className="input mb-2 w-full" value={bDevice}
                    onChange={(e) => { setBDevice(e.target.value); setBPath(""); }}>
                    <option value="">Device…</option>
                    {devices.filter((d) => d.id !== aDevice).map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                  <select className="input w-full" value={bPath} disabled={!bDevice}
                    onChange={(e) => setBPath(e.target.value)}>
                    <option value="">
                      {bDevice ? (bFolders.length ? "Folder (read & write)…" : "No read/write folders shared") : "Pick a device"}
                    </option>
                    {bFolders.map((f) => <option key={f.id} value={f.path}>{f.label || basename(f.path)}</option>)}
                  </select>
                </>
              ) : (
                <>
                  <input className="input mb-2 w-full"
                    placeholder="Colleague's email"
                    value={colleagueEmail}
                    onChange={(e) => setColleagueEmail(e.target.value)} />
                  <select className="input w-full" value={bPath} onChange={(e) => setBPath(e.target.value)}>
                    <option value="">
                      {filteredShares.length ? "Shared folder or file to sync…" : "No colleague folders with sync access"}
                    </option>
                    {filteredShares.map((s) => (
                      <option key={s.id} value={`share:${s.id}`}>
                        {s.label || basename(s.root_path)} — {s.device_name}
                        {s.owner_email ? ` (${s.owner_email})` : ""}
                      </option>
                    ))}
                  </select>
                  <p className="mt-2 text-[11px] leading-snug text-[var(--color-text-dim)]">
                    They'll get a sync request on their dashboard — once they
                    accept, the folder downloads and stays in sync.
                  </p>
                </>
              )}
            </div>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <span className="text-xs text-[var(--color-text-dim)]">Mode</span>
            <select className="input !py-1.5" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="live">Live — apply changes automatically</option>
              <option value="review">Review — stage changes first</option>
            </select>
          </div>
          {error && <p className="mt-3 text-xs text-[var(--color-danger)]">{error}</p>}
          <div className="mt-4 flex justify-end gap-2">
            <button className="btn btn-ghost" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button className="btn btn-primary" disabled={busy || !aPath || !bPath} onClick={create}>
              {busy ? <Spinner size={14} /> : <RefreshCw size={14} />} Start syncing
            </button>
          </div>
        </Modal>
      )}

      {stopTarget && (
        <ConfirmDialog
          title="Stop this sync?"
          body="Folders keep their current files but changes will no longer be copied between them."
          confirmLabel="Stop sync" danger
          onConfirm={async () => { await action(stopTarget, "stop"); setStopTarget(null); }}
          onCancel={() => setStopTarget(null)}
        />
      )}
    </div>
  );
}
