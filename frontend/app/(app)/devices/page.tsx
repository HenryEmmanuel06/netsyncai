"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft, Bot, Calendar, Check, ChevronRight, Copy, Download, Folder,
  FolderPlus, HardDrive, Laptop, Monitor, Plus, RefreshCcw, ShieldCheck, Trash2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import {
  ConfirmDialog, EmptyState, InlinePick, Modal, PageHeader, Spinner,
} from "@/components/ui";
import { basename, formatBytes, formatDate, timeAgo } from "@/lib/format";
import type { Device, LocalDirEntry, SharedFolderInfo } from "@/types";

import { useAgentDownload } from "@/lib/download";

const AGENT_DOWNLOAD_URL = process.env.NEXT_PUBLIC_AGENT_DOWNLOAD_URL ?? "";

const ACCESS_OPTIONS = [
  { value: "read", label: "Read only" },
  { value: "readwrite", label: "Read & write" },
];

interface DeviceStats {
  platform: string;
  agent_version: string;
  libreoffice: boolean;
  drives: { drive: string; total: number; free: number }[];
}

function DriveStats({ deviceId, token }: { deviceId: string; token: string }) {
  const [stats, setStats] = useState<DeviceStats | null>(null);
  useEffect(() => {
    apiFetch<DeviceStats>(`/api/v1/devices/${deviceId}/stats`, token)
      .then(setStats).catch(() => {});
  }, [deviceId, token]);
  if (!stats || stats.drives.length === 0) return null;
  const d = stats.drives[0];
  const usedPct = Math.round(((d.total - d.free) / d.total) * 100);
  return (
    <div className="mt-3">
      <div className="flex justify-between text-[11px] text-[var(--color-text-dim)]">
        <span>Storage {d.drive}</span>
        <span>{formatBytes(d.free)} free of {formatBytes(d.total)}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
        <div className={`h-full rounded-full ${usedPct > 90 ? "bg-[var(--color-danger)]" : "bg-[var(--color-primary)]"}`}
          style={{ width: `${usedPct}%` }} />
      </div>
    </div>
  );
}

function PairModal({ token, onClose }: { token: string; onClose: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dl = useAgentDownload();

  async function create() {
    if (!name.trim()) return;
    setBusy(true); setError(null);
    try {
      const r = await apiFetch<{ code: string }>("/api/v1/pairing", token, {
        method: "POST",
        body: JSON.stringify({ device_name: name.trim() }),
      });
      setCode(r.code);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
    } finally { setBusy(false); }
  }

  return (
    <Modal title="Connect a computer" onClose={onClose}>
      {AGENT_DOWNLOAD_URL ? (
        <>
          <a href={dl.url}
            className="btn btn-ghost mb-4 w-full justify-center">
            <Download size={15} /> {dl.label}
          </a>
          {dl.note && (
            <div className="mb-4 -mt-2 whitespace-pre-line rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-[11px] leading-relaxed text-[var(--color-text-dim)]">
              {dl.note}
            </div>
          )}
        </>
      ) : (
        <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs text-[var(--color-text-dim)]">
          1. Download the NetSync AI app on the computer you want to add,
          then run it.
        </div>
      )}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs text-[var(--color-text-dim)]">
        {AGENT_DOWNLOAD_URL ? "2." : "1."} Name the computer — the name is
        what you'll see across NetSync.
      </div>
      <div className="mt-3 flex gap-2">
        <input className="input flex-1" placeholder="e.g. Office Laptop"
          value={name} onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && create()} />
        <button className="btn btn-primary" onClick={create}
          disabled={busy || !name.trim()}>
          {busy ? <Spinner size={14} /> : <Plus size={14} />} Get code
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>}

      {code && (
        <div className="fade-up mt-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs text-[var(--color-text-dim)]">
            {AGENT_DOWNLOAD_URL ? "3." : "2."} Approve on that computer —
            click below if the app is already installed there:
          </div>
          <div className="mt-3 flex items-center justify-center gap-3">
            <span className="rounded-lg bg-[var(--color-surface-3)] px-5 py-2.5 font-mono text-2xl font-bold tracking-[0.3em] text-[var(--color-accent)]">
              {code}
            </span>
            <button className="btn btn-ghost" onClick={() => {
              navigator.clipboard.writeText(code); setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
          <a href={`netsync://pair?code=${code}`}
            className="btn btn-primary mt-4 w-full justify-center">
            <Monitor size={15} /> Open on the other computer (approve)
          </a>
          <p className="mt-2 text-center text-[11px] text-[var(--color-text-dim)]">
            The link opens the app with the code filled in — the person at that
            computer confirms. Valid for 10 minutes.
          </p>
        </div>
      )}
    </Modal>
  );
}

function FolderManager({ device, token, onClose }: {
  device: Device; token: string; onClose: () => void;
}) {
  const [folders, setFolders] = useState<SharedFolderInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [dirPath, setDirPath] = useState("");
  const [dirs, setDirs] = useState<LocalDirEntry[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [curBlocked, setCurBlocked] = useState<string | null>(null);
  const [access, setAccess] = useState<"read" | "readwrite">("read");
  const [busyPath, setBusyPath] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<SharedFolderInfo | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch<{ folders: SharedFolderInfo[] }>(
        `/api/v1/devices/${device.id}/folders`, token);
      setFolders(r.folders);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed");
      setFolders([]);
    }
  }, [device.id, token]);

  const loadDir = useCallback(async (path: string) => {
    try {
      const r = await apiFetch<{ path: string; parent: string | null; entries: LocalDirEntry[]; blocked?: string | null }>(
        `/api/v1/devices/${device.id}/local-dirs?path=${encodeURIComponent(path)}&files=1`, token);
      setDirPath(r.path); setParent(r.parent); setDirs(r.entries);
      setCurBlocked(r.blocked ?? null);
      setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
  }, [device.id, token]);

  useEffect(() => { load(); loadDir(""); }, [load, loadDir]);

  // poll faster while a folder is indexing so the % actually moves
  const anyIndexing = folders?.some((f) => f.indexing) ?? false;
  useEffect(() => {
    if (!anyIndexing) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [anyIndexing, load]);

  async function add(path: string) {
    setBusyPath(path);
    try {
      await apiFetch(`/api/v1/devices/${device.id}/folders`, token, {
        method: "POST",
        body: JSON.stringify({ path, access }),
      });
      await load();
      setPicker(false);
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
    finally { setBusyPath(null); }
  }

  async function changeAccess(path: string, next: string) {
    await apiFetch(`/api/v1/devices/${device.id}/folders`, token, {
      method: "PATCH",
      body: JSON.stringify({ path, access: next }),
    });
    await load();
  }

  async function remove(f: SharedFolderInfo) {
    setConfirmRemove(null);
    await apiFetch(`/api/v1/devices/${device.id}/folders/remove`, token, {
      method: "POST", body: JSON.stringify({ path: f.path }),
    });
    await load();
  }

  async function rescan(path: string) {
    setBusyPath(path);
    try {
      await apiFetch(`/api/v1/devices/${device.id}/folders/reindex`, token, {
        method: "POST", body: JSON.stringify({ path }),
      });
      await load();
    } finally { setBusyPath(null); }
  }

  return (
    <Modal title={`Shared folders — ${device.name}`} onClose={onClose} wide>
      <p className="-mt-2 mb-4 text-xs text-[var(--color-text-dim)]">
        Folders listed here are browsable (and writable with read & write) by
        you and anyone you grant on the Permissions page.
      </p>
      {error && <div className="mb-3 rounded-lg bg-[rgba(248,113,113,0.1)] px-3 py-2 text-xs text-[var(--color-danger)]">{error}</div>}

      {folders === null ? (
        <div className="py-8 text-center"><Spinner /></div>
      ) : (
        <div className="space-y-2">
          {folders.map((f) => (
            <div key={f.id} className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] px-3 py-2.5">
              <HardDrive size={16} className="shrink-0 text-[var(--color-accent)]" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{f.label || basename(f.path)}</div>
                <div className="truncate text-xs text-[var(--color-text-dim)]">
                  {f.path} · {f.file_count} files · {formatBytes(f.total_size)}
                  {f.indexing ? (
                    <>
                      {" · indexing… "}
                      {f.index_total
                        ? <span className="font-medium text-[var(--color-accent)]">
                            {Math.round(((f.index_done ?? 0) / f.index_total) * 100)}%
                          </span>
                        : <span className="text-[var(--color-accent)]">{f.index_done ?? 0} files</span>}
                    </>
                  ) : ""}
                </div>
                {f.indexing && f.index_total ? (
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
                    <div className="h-full rounded-full bg-[var(--color-accent)] transition-all"
                      style={{ width: `${Math.round(((f.index_done ?? 0) / f.index_total) * 100)}%` }} />
                  </div>
                ) : null}
              </div>
              <InlinePick className="w-36" value={f.access}
                placeholder="Access…"
                onPick={(v) => changeAccess(f.path, v)}
                options={ACCESS_OPTIONS} />
              <button className="btn btn-ghost !p-2" title="Rescan index"
                disabled={busyPath === f.path} onClick={() => rescan(f.path)}>
                {busyPath === f.path ? <Spinner size={13} /> : <RefreshCcw size={13} />}
              </button>
              <button className="btn btn-danger !p-2" title="Stop sharing"
                onClick={() => setConfirmRemove(f)}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {folders.length === 0 && (
            <div className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-xs text-[var(--color-text-dim)]">
              No folders shared from this computer yet.
            </div>
          )}
        </div>
      )}

      <div className="mt-4 border-t border-[var(--color-border)] pt-4">
        {!picker ? (
          <button className="btn btn-primary" onClick={() => setPicker(true)}>
            <FolderPlus size={15} /> Share a folder from {device.name}
          </button>
        ) : (
          <div className="fade-up">
            <div className="mb-2 flex items-center gap-2">
              <button className="btn btn-ghost !p-2" title="Up"
                disabled={!dirPath && !parent} onClick={() => loadDir(parent ?? "")}>
                <ArrowLeft size={14} />
              </button>
              <code className="flex-1 truncate text-xs text-[var(--color-text-dim)]">
                {dirPath || "Quick locations & drives"}
              </code>
              {dirPath && (
                <button className="btn btn-primary !px-3 !py-1 text-xs"
                  disabled={!!curBlocked || busyPath === dirPath}
                  title={curBlocked ?? "Share the folder you're inside"}
                  onClick={() => add(dirPath)}>
                  {busyPath === dirPath ? <Spinner size={12} /> : "Share this folder"}
                </button>
              )}
              <InlinePick className="w-36" value={access}
                placeholder="Access…"
                onPick={(v) => setAccess(v as typeof access)}
                options={ACCESS_OPTIONS} />
            </div>
            <div className="max-h-56 overflow-y-auto rounded-lg border border-[var(--color-border)]">
              {dirs.map((d) => (
                <div key={d.path}
                  className="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2 text-sm last:border-0">
                  <button className="flex flex-1 items-center gap-2 text-left hover:text-[var(--color-accent)]"
                    onClick={() => d.kind === "file" ? add(d.path) : loadDir(d.path)}
                    disabled={!!d.blocked}>
                    <HardDrive size={14} className={d.kind === "file" ? "text-[var(--color-text-dim)]" : "text-[var(--color-warn)]"} />
                    <span className="truncate">{d.name}</span>
                    {d.kind !== "file" &&
                      <ChevronRight size={14} className="ml-auto text-[var(--color-text-dim)]" />}
                  </button>
                  {d.kind !== "drive" && (
                    <button className="btn btn-ghost !px-2 !py-1 text-xs"
                      disabled={!!d.blocked || busyPath === d.path}
                      title={d.blocked ?? (d.kind === "file" ? "Share this file" : "Share this folder")}
                      onClick={() => add(d.path)}>
                      {busyPath === d.path ? <Spinner size={12} /> : "Share"}
                    </button>
                  )}
                  {d.blocked && <ShieldCheck size={13} className="text-[var(--color-text-dim)]" />}
                </div>
              ))}
              {dirs.length === 0 && (
                <div className="p-4 text-center text-xs text-[var(--color-text-dim)]">Empty folder</div>
              )}
            </div>
          </div>
        )}
      </div>

      {confirmRemove && (
        <ConfirmDialog
          title="Stop sharing this folder?"
          body={`“${confirmRemove.path}” will no longer be browsable remotely. The files themselves are not deleted.`}
          confirmLabel="Stop sharing" danger
          onConfirm={() => remove(confirmRemove)}
          onCancel={() => setConfirmRemove(null)}
        />
      )}
    </Modal>
  );
}

export default function DevicesPage() {
  const { token } = useAuth();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [pairOpen, setPairOpen] = useState(false);
  const [manage, setManage] = useState<Device | null>(null);
  const [revoking, setRevoking] = useState<Device | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    const d = await apiFetch<Device[]>("/api/v1/devices", token);
    setDevices(d.filter((x) => !x.revoked_at));
  }, [token]);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  const online = useMemo(
    () => (devices ?? []).filter((d) => d.status === "online").length,
    [devices],
  );

  async function revoke(d: Device) {
    setRevoking(null);
    await apiFetch(`/api/v1/devices/${d.id}/revoke`, token!, { method: "POST" });
    await load();
  }

  return (
    <div>
      <PageHeader
        title="Devices"
        subtitle={`${online} of ${devices?.length ?? 0} computers online`}
        actions={
          <button className="btn btn-primary" onClick={() => setPairOpen(true)}>
            <Monitor size={15} /> Add this computer
          </button>
        }
      />

      {devices === null ? (
        <div className="py-16 text-center"><Spinner /></div>
      ) : devices.length === 0 ? (
        <EmptyState
          icon={<Monitor size={20} />}
          title="No computers connected yet"
          hint="Install the NetSync AI app on a Windows PC, then pair it from here. It stays connected in the background."
          action={<button className="btn btn-primary" onClick={() => setPairOpen(true)}>Add this computer</button>}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {devices.map((d) => {
            const on = d.status === "online";
            return (
              <div key={d.id}
                className="card card-hover overflow-hidden border-[rgba(139,92,246,0.35)]"
                style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.20), rgba(59,130,246,0.06) 55%, transparent), var(--color-surface)" }}>
                <div className="flex items-start gap-4 p-5 pb-4">
                  <div className="relative flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-[rgba(139,92,246,0.4)] bg-[rgba(139,92,246,0.14)]">
                    <Laptop size={30} className="text-[var(--color-accent)]" />
                    <span className={`absolute right-2 top-2 h-2.5 w-2.5 rounded-full ${on ? "bg-[var(--color-online)]" : "bg-[var(--color-offline)]"}`} />
                  </div>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-lg font-semibold">{d.name}</div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-[var(--color-text-dim)]">
                          <span className={`h-1.5 w-1.5 rounded-full ${on ? "bg-[var(--color-online)]" : "bg-[var(--color-offline)]"}`} />
                          {on ? "Connected now" : `Last seen ${timeAgo(d.last_seen_at)}`}
                        </div>
                      </div>
                      <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
                        on
                          ? "border-[rgba(34,197,94,0.45)] bg-[rgba(34,197,94,0.08)] text-[var(--color-online)]"
                          : "border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-dim)]"
                      }`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${on ? "bg-[var(--color-online)]" : "bg-[var(--color-text-faint)]"}`} />
                        {on ? "Online" : "Offline"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* platform / agent / added info bar */}
                <div className="mx-5 flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[rgba(0,0,0,0.18)] px-3.5 py-2.5 text-[11px] text-[var(--color-text-dim)]">
                  <span className="flex items-center gap-1.5">
                    <Monitor size={13} className="text-[var(--color-accent)]" />
                    {d.platform || "—"}
                  </span>
                  <span className="h-3.5 w-px bg-[var(--color-border)]" />
                  <span className="flex items-center gap-1.5">
                    <Bot size={13} className="text-[var(--color-accent)]" />
                    Agent {d.agent_version ?? "—"}
                  </span>
                  <span className="h-3.5 w-px bg-[var(--color-border)]" />
                  <span className="flex items-center gap-1.5">
                    <Calendar size={12} className="text-[var(--color-accent)]" />
                    Added {formatDate(d.created_at)}
                  </span>
                </div>

                {on && <div className="mx-5"><DriveStats deviceId={d.id} token={token!} /></div>}

                <div className="mx-5 mb-5 mt-4 flex items-stretch gap-2">
                  <button
                    className="flex min-w-0 flex-1 items-center gap-2.5 rounded-xl border border-[var(--color-border)] bg-[rgba(0,0,0,0.18)] px-3.5 py-2.5 text-sm transition-colors hover:bg-[rgba(255,255,255,0.04)] disabled:opacity-50"
                    disabled={!on} onClick={() => setManage(d)}
                    title={!on ? "Computer is offline" : "Shared folders"}>
                    <Folder size={15} className="shrink-0 text-[var(--color-accent)]" />
                    <span className="flex-1 text-left">Folders</span>
                    <ChevronRight size={15} className="text-[var(--color-text-faint)]" />
                  </button>
                  <button title="Remove device" onClick={() => setRevoking(d)}
                    className="flex w-12 items-center justify-center rounded-xl border border-[rgba(229,72,77,0.5)] text-[#ff9ea1] transition hover:brightness-125"
                    style={{ background: "linear-gradient(135deg, rgba(229,72,77,0.85), rgba(160,26,30,0.9))" }}>
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {pairOpen && <PairModal token={token!} onClose={() => setPairOpen(false)} />}
      {manage && token && (
        <FolderManager device={manage} token={token} onClose={() => setManage(null)} />
      )}
      {revoking && (
        <ConfirmDialog
          title={`Remove ${revoking.name}?`}
          body="The app on that computer will be disconnected and show “removed from account”. You can pair it again later."
          confirmLabel="Remove device" danger
          onConfirm={() => revoke(revoking)}
          onCancel={() => setRevoking(null)}
        />
      )}
    </div>
  );
}
