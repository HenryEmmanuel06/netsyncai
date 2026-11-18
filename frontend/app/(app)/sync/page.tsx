"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight, Check, Eye, Mail, Monitor, Pause, Play, Plus, RefreshCw,
  Square, Users, Zap,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import {
  ConfirmDialog, Dropdown, EmptyState, Field, FolderArt, Modal, PageHeader, Spinner,
} from "@/components/ui";
import { basename, formatBytes } from "@/lib/format";
import type { Device, SharedFolder, SharedFolderInfo, SyncSession } from "@/types";

interface LiveSync { applied_ops: number; pending_ops: number; sides: { device_id: string; name?: string; online: boolean; gone?: boolean; paused: boolean }[] }

function useLive(sessionId: string, token: string, enabled: boolean) {
  const [live, setLive] = useState<LiveSync | null>(null);
  useEffect(() => {
    if (!enabled) { setLive(null); return; }
    let alive = true;
    const load = () => apiFetch<LiveSync>(`/api/v1/sync/${sessionId}/live`, token)
      .then((r) => alive && setLive(r)).catch(() => {});
    load();
    const t = setInterval(load, 10000);
    return () => { alive = false; clearInterval(t); };
  }, [sessionId, token, enabled]);
  return live;
}

const STATE_META: Record<string, { label: string; cls: string }> = {
  active: { label: "Syncing", cls: "badge-green" },
  paused: { label: "Paused", cls: "badge-amber" },
  error: { label: "Needs attention", cls: "badge-red" },
  pending: { label: "Waiting for acceptance", cls: "badge-blue" },
  stopped: { label: "Stopped", cls: "badge-gray" },
};

function SessionCard({ s, token, deviceName, onAction, onStop }: {
  s: SyncSession; token: string; deviceName: (id: string) => string;
  onAction: (s: SyncSession, act: "pause" | "resume") => void;
  onStop: (s: SyncSession) => void;
}) {
  const live = useLive(s.id, token, s.state === "active" || s.state === "paused");
  const meta = STATE_META[s.state] ?? { label: s.state, cls: "badge-gray" };
  const [a, b] = s.participants;
  const title = basename(a?.root ?? "") || "Sync";
  const sideOnline = (id?: string) => live?.sides.find((x) => x.device_id === id)?.online;

  // real liveness: "active" only counts when every side is actually running
  // the session — a dead peer means the sync is broken, not syncing
  const deadSide = s.state === "active" ? live?.sides.find((x) => x.gone) : undefined;
  const offSide = s.state === "active" ? live?.sides.find((x) => !x.gone && !x.online) : undefined;
  const badge = s.state === "active" && live
    ? deadSide
      ? { label: "Peer device removed", cls: "badge-red" }
      : offSide
        ? { label: `Waiting for ${offSide.name || deviceName(offSide.device_id)}`, cls: "badge-amber" }
        : meta
    : meta;

  return (
    <div className="card card-hover flex flex-col overflow-hidden">
      <div className="flex items-start gap-3 p-4">
        <FolderArt size={46} tone={s.state === "active" ? "orange" : s.state === "pending" ? "blue" : "purple"} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{title}</div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className={`badge ${badge.cls}`}>
              {s.state === "active" && !deadSide && !offSide && <RefreshCw size={10} className="spin-slow" />}
              {badge.label}
            </span>
            <span className="pill">{s.mode === "review" ? "Review mode" : "Live"}</span>
          </div>
        </div>
      </div>

      {/* the two endpoints joined by a connector */}
      <div className="mx-4 mb-4 flex items-center gap-2">
        {[a, b].map((p, i) => (
          <div key={p?.device_id ?? i} className={`well min-w-0 flex-1 px-3 py-2.5 ${i === 1 ? "order-3" : ""}`}>
            <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-faint)]">
              <Monitor size={11} />
              <span className="truncate">{p ? deviceName(p.device_id) : "—"}</span>
              {live && (
                <span className={`ml-auto h-1.5 w-1.5 shrink-0 rounded-full ${sideOnline(p?.device_id) ? "bg-[var(--color-online)]" : "bg-[var(--color-offline)]"}`} />
              )}
            </div>
            <div className="mt-0.5 truncate text-[13px] font-medium">{p ? basename(p.root) || p.root : "—"}</div>
          </div>
        ))}
        <span className={`order-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${
          s.state === "active"
            ? "border-[rgba(139,92,246,0.5)] bg-[rgba(139,92,246,0.12)] text-[var(--color-accent)]"
            : "border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-faint)]"
        }`}>
          <ArrowLeftRight size={13} />
        </span>
      </div>

      {(deadSide || offSide) && (
        <div className="mx-4 mb-4 rounded-md border border-[rgba(251,191,36,0.25)] bg-[rgba(251,191,36,0.08)] px-3 py-2 text-[11px] leading-snug text-[var(--color-text-dim)]">
          {deadSide
            ? "The other device no longer exists — stop this sync and start a new one between your current devices."
            : `${offSide!.name || deviceName(offSide!.device_id)} is offline. The sync resumes automatically when it reconnects.`}
        </div>
      )}

      <div className="mt-auto grid grid-cols-3 border-t border-[var(--color-border)] bg-[rgba(0,0,0,0.15)] text-[11px]">
        {[
          { k: "Applied", v: live ? live.applied_ops : "—" },
          { k: "Pending", v: live ? live.pending_ops : "—" },
          { k: "Sides live", v: live ? `${live.sides.filter((x) => x.online).length}/${live.sides.length}` : "—" },
        ].map((m, i) => (
          <div key={m.k} className={`px-3 py-2.5 ${i > 0 ? "border-l border-[var(--color-border)]" : ""}`}>
            <div className="text-[var(--color-text-faint)]">{m.k}</div>
            <div className="mt-0.5 text-sm font-semibold">{m.v}</div>
          </div>
        ))}
      </div>

      {s.state !== "stopped" && (
        <div className="flex gap-2 border-t border-[var(--color-border)] px-3 py-2.5">
          {s.state === "active" && (
            <button className="btn btn-ghost flex-1 !py-1.5 !text-xs" onClick={() => onAction(s, "pause")}>
              <Pause size={12} /> Pause
            </button>
          )}
          {s.state === "paused" && (
            <button className="btn btn-primary flex-1 !py-1.5 !text-xs" onClick={() => onAction(s, "resume")}>
              <Play size={12} /> Resume
            </button>
          )}
          <button className={`btn btn-danger !py-1.5 !text-xs ${s.state === "active" || s.state === "paused" ? "" : "flex-1"}`}
            onClick={() => onStop(s)}>
            <Square size={11} /> {s.state === "pending" ? "Cancel request" : "Stop"}
          </button>
        </div>
      )}
    </div>
  );
}

/** Selectable folder row used in the New-sync modal. */
function FolderOption({ active, onClick, title, sub, meta }: {
  active: boolean; onClick: () => void; title: string; sub?: string; meta?: string;
}) {
  return (
    <button type="button" onClick={onClick} data-active={active}
      className="option-card flex w-full items-center gap-3 !p-2.5">
      <FolderArt size={30} tone={active ? "orange" : "purple"} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">{title}</div>
        {sub && <div className="truncate text-[11px] text-[var(--color-text-faint)]">{sub}</div>}
      </div>
      {meta && <span className="pill shrink-0">{meta}</span>}
      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
        active ? "border-[var(--color-primary)] bg-[var(--color-primary)]" : "border-[var(--color-border-strong)]"
      }`}>
        {active && <Check size={10} className="text-white" />}
      </span>
    </button>
  );
}

function FolderList({ empty, children }: { empty?: string; children: React.ReactNode }) {
  return (
    <div className="max-h-52 space-y-1.5 overflow-y-auto pr-0.5">
      {children}
      {empty && (
        <div className="well dots px-3 py-6 text-center text-[11px] leading-relaxed text-[var(--color-text-dim)]">
          {empty}
        </div>
      )}
    </div>
  );
}

function folderMeta(f: SharedFolderInfo) {
  return f.file_count ? `${f.file_count} · ${formatBytes(f.total_size)}` : undefined;
}

type SyncRequest = SyncSession & {
  my_device_name?: string; my_root?: string; needs_folder?: boolean;
};

/** Incoming sync-request banner. Requests addressed to the recipient by
 *  email need them to pick the local folder before accepting. */
function RequestCard({ r, devices, token, onRespond }: {
  r: SyncRequest; devices: Device[]; token: string;
  onRespond: (id: string, accept: boolean,
              dest?: { device_id: string; root_path?: string;
                       to_downloads?: boolean }) => void;
}) {
  const [dev, setDev] = useState("");
  const [folders, setFolders] = useState<SharedFolderInfo[] | null>(null);
  const [root, setRoot] = useState("");
  const [destKind, setDestKind] = useState<"downloads" | "pick">("downloads");
  const [ownDevices, setOwnDevices] = useState<Device[]>(devices);

  // the request can arrive before the page's device fetch lands — fall
  // back to fetching our own devices so the picker is never empty
  useEffect(() => { setOwnDevices(devices); }, [devices]);
  useEffect(() => {
    if (devices.length || !r.needs_folder) return;
    apiFetch<Device[]>("/api/v1/devices", token)
      .then((d) => setOwnDevices(d.filter((x) => !x.revoked_at)))
      .catch(() => {});
  }, [devices.length, r.needs_folder, token]);

  useEffect(() => {
    if (!dev || !token) { setFolders(null); return; }
    setFolders(null);
    apiFetch<{ folders: SharedFolderInfo[] }>(
      `/api/v1/devices/${dev}/folders`, token)
      .then((x) => setFolders(x.folders.filter((f) => f.access === "readwrite")))
      .catch(() => setFolders([]));
  }, [dev, token]);

  const src = basename(r.name.split("↔")[0]?.trim() || r.name);

  return (
    <div className="pop-in relative mb-4 overflow-hidden rounded-2xl bg-gradient-to-r from-[rgba(139,92,246,0.55)] via-[rgba(192,107,255,0.35)] to-[rgba(255,154,61,0.45)] p-px">
      <div className="rounded-[15px] bg-[var(--color-surface)] p-4">
        <div className="flex flex-wrap items-center gap-4">
          <FolderArt size={48} tone="blue" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">Sync request</span>
              <span className="badge badge-purple">New</span>
            </div>
            <div className="mt-1 text-xs leading-relaxed text-[var(--color-text-dim)]">
              {r.needs_folder ? (
                <>
                  A colleague wants to sync <span className="font-medium text-[var(--color-text)]">{src}</span> with you.
                  Accepting downloads it to your PC and keeps both sides in sync.
                </>
              ) : (
                <>
                  A colleague wants to sync <span className="font-medium text-[var(--color-text)]">{src}</span>
                  {" "}with <span className="font-medium text-[var(--color-text)]">{basename(r.my_root ?? "")}</span> on {r.my_device_name}.
                  Accepting downloads their content to your PC and keeps it in sync.
                </>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-ghost" onClick={() => onRespond(r.id, false)}>Decline</button>
            <button className="btn btn-primary"
              disabled={!!r.needs_folder && (!dev || (destKind === "pick" && !root))}
              onClick={() => onRespond(r.id, true,
                r.needs_folder
                  ? destKind === "downloads"
                    ? { device_id: dev, to_downloads: true }
                    : { device_id: dev, root_path: root }
                  : undefined)}>
              <Check size={14} /> Accept & sync
            </button>
          </div>
        </div>

        {r.needs_folder && (
          <div className="mt-3 space-y-2 border-t border-[var(--color-border)] pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <Monitor size={13} className="text-[var(--color-text-faint)]" />
              <Dropdown className="w-48 text-xs" value={dev}
                placeholder="Your computer…"
                onChange={(v) => { setDev(v); setRoot(""); }}
                options={ownDevices.map((d) => ({
                  value: d.id, label: d.name,
                  hint: d.status !== "online" ? "offline" : "online",
                }))} />
              {dev && (
                <div className="flex overflow-hidden rounded-lg border border-[var(--color-border)] text-xs">
                  <button
                    className={`px-3 py-1.5 transition ${destKind === "downloads" ? "bg-[var(--color-accent)] text-white" : "bg-[var(--color-surface-2)] text-[var(--color-text-dim)]"}`}
                    onClick={() => setDestKind("downloads")}>
                    New folder in Downloads
                  </button>
                  <button
                    className={`px-3 py-1.5 transition ${destKind === "pick" ? "bg-[var(--color-accent)] text-white" : "bg-[var(--color-surface-2)] text-[var(--color-text-dim)]"}`}
                    onClick={() => setDestKind("pick")}>
                    Existing folder
                  </button>
                </div>
              )}
            </div>
            {dev && destKind === "downloads" && (
              <p className="text-[11px] text-[var(--color-text-faint)]">
                A new folder <span className="font-medium text-[var(--color-text)]">Downloads\{src}</span> will be created on that PC and kept in sync.
              </p>
            )}
            {dev && destKind === "pick" && (
              folders === null ? <Spinner size={14} /> : (
                <Dropdown className="w-56 text-xs" value={root}
                  placeholder="Shared folder to sync into…"
                  onChange={(v) => setRoot(v)}
                  options={folders.map((f) => ({
                    value: f.path, label: f.label || basename(f.path),
                  }))} />
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SyncPage() {
  const { token } = useAuth();
  const [sessions, setSessions] = useState<SyncSession[] | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [shares, setShares] = useState<SharedFolder[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [aDevice, setADevice] = useState("");
  const [aFolders, setAFolders] = useState<SharedFolderInfo[] | null>(null);
  const [aPath, setAPath] = useState("");
  const [bKind, setBKind] = useState<"mine" | "colleague">("mine");
  const [bDevice, setBDevice] = useState("");
  const [bFolders, setBFolders] = useState<SharedFolderInfo[] | null>(null);
  const [bPath, setBPath] = useState("");
  const [mode, setMode] = useState("live");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [colleagueEmail, setColleagueEmail] = useState("");
  const [stopTarget, setStopTarget] = useState<SyncSession | null>(null);
  const [tab, setTab] = useState<"active" | "paused" | "stopped">("active");
  const [requests, setRequests] = useState<SyncRequest[]>([]);

  const load = useCallback(async () => {
    if (!token) return;
    const [s, d, sh, req] = await Promise.all([
      apiFetch<SyncSession[]>("/api/v1/sync", token),
      apiFetch<Device[]>("/api/v1/devices", token),
      apiFetch<{ granted: SharedFolder[] }>("/api/v1/sharing", token).catch(() => ({ granted: [] })),
      apiFetch<{ requests: SyncRequest[] }>(
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
    if (!id || !token) { setBFolders(null); return; }
    setBFolders(null);
    apiFetch<{ folders: SharedFolderInfo[] }>(`/api/v1/devices/${id}/folders`, token)
      .then((r) => setBFolders(r.folders.filter((f) => f.access === "readwrite")))
      .catch(() => setBFolders([]));
  }, [bDevice, bKind, token]);

  useEffect(() => {
    if (!aDevice || !token) { setAFolders(null); return; }
    setAFolders(null);
    apiFetch<{ folders: SharedFolderInfo[] }>(`/api/v1/devices/${aDevice}/folders`, token)
      .then((r) => setAFolders(r.folders.filter((f) => f.access === "readwrite")))
      .catch(() => setAFolders([]));
  }, [aDevice, token]);

  function openCreate() {
    setError(null);
    if (!aDevice) {
      const first = devices.find((d) => d.status === "online") ?? devices[0];
      if (first) setADevice(first.id);
    }
    setCreateOpen(true);
  }

  async function create() {
    if (!aDevice || !aPath) return;
    let body: Record<string, unknown>;
    if (bKind === "mine") {
      if (!bDevice || !bPath) return;
      body = { a_device_id: aDevice, a_path: aPath,
               b_device_id: bDevice, b_path: bPath, mode };
    } else if (bShare) {
      // they've granted me sync access on this folder — sync straight into it
      body = { a_device_id: aDevice, a_path: aPath,
               b_device_id: bShare.device_id, b_path: bShare.root_path, mode };
    } else {
      // send the request by email — they choose their folder on accept
      if (!emailOk) return;
      body = { a_device_id: aDevice, a_path: aPath,
               b_user: colleagueEmail.trim(), mode };
    }
    setBusy(true); setError(null);
    try {
      await apiFetch("/api/v1/sync", token!, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setCreateOpen(false);
      setAPath(""); setBPath(""); setColleagueEmail("");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
    finally { setBusy(false); }
  }

  async function respondToRequest(
    id: string, accept: boolean,
    dest?: { device_id: string; root_path?: string; to_downloads?: boolean },
  ) {
    try {
      await apiFetch(`/api/v1/sync/${id}/${accept ? "accept" : "decline"}`,
        token!, { method: "POST", body: dest ? JSON.stringify(dest) : undefined });
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
    return (id: string) => m.get(id) ?? "Colleague's computer";
  }, [devices]);

  const filteredShares = useMemo(() => {
    const q = colleagueEmail.trim().toLowerCase();
    if (!q) return shares;
    return shares.filter((s) =>
      (s.owner_email ?? "").toLowerCase().includes(q));
  }, [shares, colleagueEmail]);

  const inTab = (s: SyncSession, k: typeof tab) =>
    k === "active" ? ["active", "pending", "error"].includes(s.state) : s.state === k;

  const aLabel = aFolders?.find((f) => f.path === aPath);
  const bShare = shares.find((s) => `share:${s.id}` === bPath);
  const emailOk = /^\S+@\S+\.\S+$|^@[\w.-]+$/.test(colleagueEmail.trim());
  const bLabel = bKind === "mine"
    ? bFolders?.find((f) => f.path === bPath)?.label || basename(bPath)
    : bShare?.label || basename(bShare?.root_path ?? "") || colleagueEmail.trim();
  const ready = !!aPath && (bKind === "mine" ? !!bPath : !!bPath || emailOk);

  return (
    <div>
      <PageHeader
        title="Synchronization"
        subtitle="Keep folders identical across computers — yours or a colleague's."
        actions={
          <button className="btn btn-primary" onClick={openCreate}>
            <Plus size={15} /> New sync
          </button>
        }
      />

      {error && !createOpen && (
        <div className="card mb-4 border-[rgba(248,113,113,0.3)] px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div>
      )}

      {/* incoming sync requests — what the other user sees */}
      {requests.map((r) => (
        <RequestCard key={r.id} r={r} devices={devices} token={token!}
          onRespond={respondToRequest} />
      ))}

      {sessions !== null && sessions.length > 0 && (
        <div className="segmented mb-5">
          {(["active", "paused", "stopped"] as const).map((k) => (
            <button key={k} className={`tab ${tab === k ? "tab-active" : ""}`} onClick={() => setTab(k)}>
              {k === "active" ? "Active" : k === "paused" ? "Paused" : "Stopped"}
              <span className="pill !px-1.5 !py-0 !text-[10px]">{sessions.filter((s) => inTab(s, k)).length}</span>
            </button>
          ))}
        </div>
      )}

      {sessions === null ? (
        <div className="py-16 text-center"><Spinner /></div>
      ) : sessions.length === 0 ? (
        <EmptyState
          art={<div className="mb-2"><FolderArt size={84} /></div>}
          title="No sync sessions yet"
          hint="Link two folders — changes on either side appear on the other within seconds."
          action={<button className="btn btn-primary" onClick={openCreate}><Plus size={14} /> New sync</button>}
        />
      ) : sessions.filter((s) => inTab(s, tab)).length === 0 ? (
        <div className="card dots px-6 py-12 text-center text-sm text-[var(--color-text-dim)]">
          Nothing {tab} right now.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sessions.filter((s) => inTab(s, tab)).map((s) => (
            <SessionCard key={s.id} s={s} token={token!} deviceName={deviceName}
              onAction={action} onStop={setStopTarget} />
          ))}
        </div>
      )}

      {createOpen && (
        <Modal wide title="New sync" icon={<RefreshCw size={16} />}
          subtitle="Pick a folder on each side. Changes on either side are copied to the other — deletions never are."
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <span className="mr-auto min-w-0 truncate text-xs text-[var(--color-text-faint)]">
                {ready
                  ? <><span className="text-[var(--color-text)]">{aLabel?.label || basename(aPath)}</span> ↔ <span className="text-[var(--color-text)]">{bLabel}</span>{bKind === "colleague" && " · needs their approval"}</>
                  : bKind === "colleague" ? "Choose your folder and enter their email" : "Choose a folder on both sides"}
              </span>
              <button className="btn btn-ghost" onClick={() => setCreateOpen(false)}>Cancel</button>
              <button className="btn btn-primary" disabled={busy || !ready} onClick={create}>
                {busy ? <Spinner size={14} /> : bKind === "colleague" ? <Mail size={14} /> : <RefreshCw size={14} />}
                {bKind === "colleague" ? "Send sync request" : "Start syncing"}
              </button>
            </>
          }>
          <div className="grid items-stretch gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
            {/* side A */}
            <div className="well min-w-0 space-y-3 p-3.5">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-primary)] text-[10px] font-bold text-white">1</span>
                <span className="text-[13px] font-semibold">Your folder</span>
              </div>
              <Field label="Computer">
                <Dropdown className="w-full" value={aDevice}
                  placeholder="Choose a computer…"
                  onChange={(v) => { setADevice(v); setAPath(""); }}
                  options={devices.map((d) => ({
                    value: d.id, label: d.name,
                    hint: d.status !== "online" ? "offline" : "online",
                  }))} />
              </Field>
              <div>
                <label className="field-label">Folder or file</label>
                {!aDevice ? (
                  <FolderList empty="Pick a computer first" >{null}</FolderList>
                ) : aFolders === null ? (
                  <div className="py-6 text-center"><Spinner /></div>
                ) : (
                  <FolderList empty={aFolders.length ? undefined : "No read & write folders on this computer — share one under Devices → Folders with Read & write."}>
                    {aFolders.map((f) => (
                      <FolderOption key={f.id} active={aPath === f.path} onClick={() => setAPath(f.path)}
                        title={f.label || basename(f.path)} sub={f.path} meta={folderMeta(f)} />
                    ))}
                  </FolderList>
                )}
              </div>
            </div>

            {/* connector */}
            <div className="flex items-center justify-center md:flex-col">
              <span className="hidden h-full w-px bg-gradient-to-b from-transparent via-[var(--color-border-strong)] to-transparent md:block" />
              <span className={`my-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-colors ${
                ready
                  ? "border-[rgba(139,92,246,0.6)] bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)] shadow-[0_0_20px_-4px_rgba(139,92,246,0.6)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-faint)]"
              }`}>
                <ArrowLeftRight size={16} />
              </span>
              <span className="hidden h-full w-px bg-gradient-to-b from-transparent via-[var(--color-border-strong)] to-transparent md:block" />
            </div>

            {/* side B */}
            <div className="well min-w-0 space-y-3 p-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-primary)] text-[10px] font-bold text-white">2</span>
                  <span className="text-[13px] font-semibold">Sync with</span>
                </div>
                <div className="segmented !p-0.5">
                  <button type="button" className={`tab !px-2.5 !py-1 !text-[11px] ${bKind === "mine" ? "tab-active" : ""}`}
                    onClick={() => { setBKind("mine"); setBPath(""); setBDevice(""); }}>
                    <Monitor size={11} /> My PC
                  </button>
                  <button type="button" className={`tab !px-2.5 !py-1 !text-[11px] ${bKind === "colleague" ? "tab-active" : ""}`}
                    onClick={() => { setBKind("colleague"); setBPath(""); setBDevice(""); }}>
                    <Users size={11} /> Colleague
                  </button>
                </div>
              </div>

              {bKind === "mine" ? (
                <>
                  <Field label="Computer">
                    <Dropdown className="w-full" value={bDevice}
                      placeholder="Choose another computer…"
                      onChange={(v) => { setBDevice(v); setBPath(""); }}
                      options={devices.filter((d) => d.id !== aDevice).map((d) => ({
                        value: d.id, label: d.name,
                        hint: d.status !== "online" ? "offline" : "online",
                      }))} />
                  </Field>
                  <div>
                    <label className="field-label">Folder or file</label>
                    {!bDevice ? (
                      <FolderList empty={devices.length > 1 ? "Pick a computer first" : "You only have one computer — switch to Colleague, or connect another PC."}>{null}</FolderList>
                    ) : bFolders === null ? (
                      <div className="py-6 text-center"><Spinner /></div>
                    ) : (
                      <FolderList empty={bFolders.length ? undefined : "No read & write folders on this computer yet."}>
                        {bFolders.map((f) => (
                          <FolderOption key={f.id} active={bPath === f.path} onClick={() => setBPath(f.path)}
                            title={f.label || basename(f.path)} sub={f.path} meta={folderMeta(f)} />
                        ))}
                      </FolderList>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <Field label="Colleague's email">
                    <label className="input flex items-center gap-2">
                      <Mail size={14} className="shrink-0 text-[var(--color-text-faint)]" />
                      <input className="min-w-0 flex-1 bg-transparent outline-none"
                        placeholder="name@company.com" value={colleagueEmail}
                        onChange={(e) => setColleagueEmail(e.target.value)} />
                    </label>
                  </Field>
                  <div>
                    <label className="field-label">Their shared folder or file <span className="font-normal normal-case text-[var(--color-text-faint)]">(optional)</span></label>
                    <FolderList empty={filteredShares.length ? undefined
                      : "No folders yet — that's fine, just send the request and they'll pick where it lands on their PC."}>
                      {filteredShares.map((s) => (
                        <FolderOption key={s.id} active={bPath === `share:${s.id}`}
                          onClick={() => setBPath(`share:${s.id}`)}
                          title={s.label || basename(s.root_path)}
                          sub={`${s.device_name}${s.owner_email ? ` · ${s.owner_email}` : ""}`} />
                      ))}
                    </FolderList>
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="mt-4">
            <label className="field-label">How changes are applied</label>
            <div className="grid gap-2 sm:grid-cols-2">
              {[
                { key: "live", icon: <Zap size={15} />, title: "Live", desc: "Changes are copied automatically within seconds." },
                { key: "review", icon: <Eye size={15} />, title: "Review", desc: "Incoming changes are staged so you can check them first." },
              ].map((m) => (
                <button key={m.key} type="button" data-active={mode === m.key}
                  className="option-card flex items-start gap-3" onClick={() => setMode(m.key)}>
                  <span className={`mt-0.5 ${mode === m.key ? "text-[var(--color-accent)]" : "text-[var(--color-text-faint)]"}`}>{m.icon}</span>
                  <span>
                    <span className="block text-[13px] font-semibold">{m.title}</span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-[var(--color-text-dim)]">{m.desc}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          {bKind === "colleague" && (
            <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-[rgba(96,165,250,0.25)] bg-[rgba(96,165,250,0.06)] px-3 py-2.5 text-[11px] leading-relaxed text-[var(--color-text-dim)]">
              <Mail size={13} className="mt-0.5 shrink-0 text-[#8ec0fb]" />
              They&apos;ll get a sync request on their dashboard. Once they accept, the folder downloads to their PC and stays in sync.
            </div>
          )}
          {error && <p className="mt-3 text-xs text-[var(--color-danger)]">{error}</p>}
        </Modal>
      )}

      {stopTarget && (
        <ConfirmDialog
          title={stopTarget.state === "pending" ? "Cancel this request?" : "Stop this sync?"}
          body="Folders keep their current files but changes will no longer be copied between them."
          confirmLabel={stopTarget.state === "pending" ? "Cancel request" : "Stop sync"} danger
          onConfirm={async () => { await action(stopTarget, "stop"); setStopTarget(null); }}
          onCancel={() => setStopTarget(null)}
        />
      )}
    </div>
  );
}
