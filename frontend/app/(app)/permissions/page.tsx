"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUp, Ban, Check, Eye, FileText, Folder, FolderPlus, Inbox, Pencil,
  RefreshCw, Search, ShieldCheck, UserPlus, X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import {
  ConfirmDialog, EmptyState, Modal, PageHeader, PermBadges, Spinner,
} from "@/components/ui";
import { basename, initials, timeAgo } from "@/lib/format";
import type { Device, GrantEntry, SharedFolder, SharedFolderInfo } from "@/types";

interface AccessRequest {
  id: string;
  requester_id: string;
  requester_email?: string | null;
  folder_id: string;
  folder_label: string;
  device_name: string;
  role: string;
  status: string;
  created_at: string;
}

interface BlockedUser { user_id: string; email?: string | null }

const ROLES = [
  { key: "viewer", label: "Viewer", icon: Eye,
    bits: 1 | 2,
    desc: "Browse and download files" },
  { key: "editor", label: "Editor", icon: Pencil,
    bits: 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128,
    desc: "Everything except sharing & sync" },
  { key: "manager", label: "Manager", icon: ShieldCheck,
    bits: 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 1024,
    desc: "Full access incl. folder sync" },
] as const;

interface BrowseEntry { name: string; path: string; kind: "dir" | "file" | "quick" | "drive"; blocked?: string | null }

function PathBrowser({ deviceId, token, selected, onPick }: {
  deviceId: string; token: string;
  selected: string; onPick: (p: string) => void;
}) {
  const [cur, setCur] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [busyDirs, setBusyDirs] = useState(false);

  const open = useCallback(async (p: string) => {
    setBusyDirs(true);
    try {
      const r = await apiFetch<{ path: string; parent: string | null; entries: BrowseEntry[] }>(
        `/api/v1/devices/${deviceId}/local-dirs?path=${encodeURIComponent(p)}&files=1`,
        token,
      );
      setCur(r.path); setParent(r.parent); setEntries(r.entries);
    } catch { setEntries([]); }
    finally { setBusyDirs(false); }
  }, [deviceId, token]);

  useEffect(() => { open(""); }, [open]);

  return (
    <div className="rounded-lg border border-[var(--color-border)]">
      <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2">
        <button className="btn btn-ghost !p-1" title="Up"
          disabled={!parent} onClick={() => parent && open(parent)}>
          <ArrowUp size={12} />
        </button>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--color-text-dim)]">
          {cur || "Pick a location"}
        </span>
        {cur && cur !== "" && (
          <button className="btn btn-ghost !px-2 !py-1 text-xs"
            onClick={() => onPick(cur)}>
            Select this folder
          </button>
        )}
      </div>
      <div className="max-h-56 overflow-y-auto p-1">
        {busyDirs ? (
          <div className="py-6 text-center"><Spinner /></div>
        ) : entries.length === 0 ? (
          <div className="py-6 text-center text-xs text-[var(--color-text-dim)]">Empty</div>
        ) : (
          entries.map((e) => (
            <div key={e.path} className="group flex items-center">
              <button
                className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors ${
                  selected === e.path
                    ? "bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)]"
                    : "hover:bg-[var(--color-surface-2)]"
                }`}
                onClick={() => e.kind === "file" ? onPick(e.path) : open(e.path)}>
                {e.kind === "file"
                  ? <FileText size={13} className="shrink-0 text-[var(--color-text-dim)]" />
                  : <Folder size={13} className={`shrink-0 ${e.blocked ? "text-[var(--color-danger)]" : "text-[var(--color-warn)]"}`} />}
                <span className="truncate">{e.name}</span>
                {e.blocked && <span className="badge badge-red ml-auto">protected</span>}
              </button>
              {e.kind === "file" ? null : (
                <button
                  className="mr-1 shrink-0 rounded px-2 py-1 text-[10px] text-[var(--color-accent)] opacity-0 transition-opacity hover:bg-[var(--color-surface-2)] group-hover:opacity-100"
                  onClick={() => !e.blocked && onPick(e.path)}>
                  Share
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function bitsToRole(bits: number): string {
  if ((bits & 256) !== 0) return "manager";
  if ((bits & 4) !== 0) return "editor";
  return "viewer";
}

export default function PermissionsPage() {
  const { token } = useAuth();
  const [devices, setDevices] = useState<Device[]>([]);
  const [owned, setOwned] = useState<SharedFolder[]>([]);
  const [granted, setGranted] = useState<SharedFolder[]>([]);
  const [selected, setSelected] = useState<SharedFolder | null>(null);
  const [grants, setGrants] = useState<GrantEntry[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [subject, setSubject] = useState("");
  const [role, setRole] = useState<string>("viewer");
  const [shareOpen, setShareOpen] = useState(false);
  const [pickDevice, setPickDevice] = useState("");
  const [pickFolder, setPickFolder] = useState("");
  const [pickAccess, setPickAccess] = useState<"read" | "readwrite">("read");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState<SharedFolder | null>(null);
  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState<"folders" | "requests" | "blocked">("folders");
  const [requests, setRequests] = useState<{ incoming: AccessRequest[]; outgoing: AccessRequest[] } | null>(null);
  const [blocked, setBlocked] = useState<BlockedUser[] | null>(null);
  const [blockSubject, setBlockSubject] = useState("");
  const [approveRole, setApproveRole] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (!token) return;
    const [devs, shares] = await Promise.all([
      apiFetch<Device[]>("/api/v1/devices", token),
      apiFetch<{ owned: SharedFolder[]; granted: SharedFolder[] }>("/api/v1/sharing", token),
    ]);
    setDevices(devs.filter((d) => !d.revoked_at));
    setOwned(shares.owned);
    setGranted(shares.granted);
    const [req, bl] = await Promise.all([
      apiFetch<{ incoming: AccessRequest[]; outgoing: AccessRequest[] }>(
        "/api/v1/sharing/requests", token).catch(() => null),
      apiFetch<{ blocked: BlockedUser[] }>("/api/v1/sharing/blocks", token)
        .catch(() => null),
    ]);
    setRequests(req);
    setBlocked(bl?.blocked ?? []);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!selected || !token) return;
    apiFetch<GrantEntry[]>(`/api/v1/sharing/${selected.id}/grants`, token)
      .then(setGrants).catch(() => setGrants([]));
  }, [selected, token]);

  async function createShare() {
    if (!pickFolder || !pickDevice) return;
    setBusy(true); setError(null);
    try {
      // 1. register the folder/file with the agent (it starts indexing)
      await apiFetch(`/api/v1/devices/${pickDevice}/folders`, token!, {
        method: "POST",
        body: JSON.stringify({
          path: pickFolder, access: pickAccess,
          label: label || basename(pickFolder),
        }),
      });
      // 2. create the share record so it can be granted to colleagues
      await apiFetch("/api/v1/sharing", token!, {
        method: "POST",
        body: JSON.stringify({
          device_id: pickDevice, root_path: pickFolder,
          label: label || basename(pickFolder),
        }),
      });
      setShareOpen(false); setPickFolder(""); setLabel(""); setPickAccess("read");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
    finally { setBusy(false); }
  }

  async function addGrant() {
    if (!selected || !subject.trim()) return;
    setBusy(true); setError(null);
    const bits = ROLES.find((r) => r.key === role)!.bits;
    try {
      await apiFetch(`/api/v1/sharing/${selected.id}/grants`, token!, {
        method: "POST",
        body: JSON.stringify({ subject: subject.trim(), permissions: bits }),
      });
      setSubject(""); setAddOpen(false);
      const g = await apiFetch<GrantEntry[]>(`/api/v1/sharing/${selected.id}/grants`, token!);
      setGrants(g);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "grant failed"); }
    finally { setBusy(false); }
  }

  async function changeRole(g: GrantEntry, next: string) {
    await apiFetch(`/api/v1/sharing/${selected!.id}/grants/${g.id}`, token!, { method: "DELETE" });
    const bits = ROLES.find((r) => r.key === next)!.bits;
    await apiFetch(`/api/v1/sharing/${selected!.id}/grants`, token!, {
      method: "POST",
      body: JSON.stringify({ subject: g.subject_user_id, permissions: bits }),
    });
    const g2 = await apiFetch<GrantEntry[]>(`/api/v1/sharing/${selected!.id}/grants`, token!);
    setGrants(g2);
  }

  async function revokeGrant(g: GrantEntry) {
    await apiFetch(`/api/v1/sharing/${selected!.id}/grants/${g.id}`, token!, { method: "DELETE" });
    setGrants(grants.filter((x) => x.id !== g.id));
  }

  async function resolveRequest(id: string, approve: boolean) {
    const role = approveRole[id] ?? "viewer";
    await apiFetch(`/api/v1/sharing/requests/${id}/${approve ? "approve" : "deny"}`, token!, {
      method: "POST",
      body: approve ? JSON.stringify({ role }) : undefined,
    }).then(load).catch((e) => setError(e instanceof Error ? e.message : "failed"));
  }

  async function requestUpgrade(s: SharedFolder) {
    await apiFetch(`/api/v1/sharing/${s.id}/request`, token!, {
      method: "POST", body: JSON.stringify({ role: "editor" }),
    }).then(load).catch((e) => setError(e instanceof Error ? e.message : "failed"));
  }

  async function blockUser() {
    if (!blockSubject.trim()) return;
    setBusy(true); setError(null);
    try {
      await apiFetch("/api/v1/sharing/blocks", token!, {
        method: "POST", body: JSON.stringify({ subject: blockSubject.trim() }),
      });
      setBlockSubject("");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "failed"); }
    finally { setBusy(false); }
  }

  async function unblockUser(uid: string) {
    await apiFetch(`/api/v1/sharing/blocks/${uid}`, token!, { method: "DELETE" })
      .then(load).catch(() => {});
  }

  async function stopSharing(s: SharedFolder) {
    setConfirmStop(null);
    await apiFetch(`/api/v1/sharing/${s.id}`, token!, { method: "DELETE" });
    if (selected?.id === s.id) setSelected(null);
    await load();
  }

  const filtered = owned.filter((s) =>
    (s.label + s.root_path).toLowerCase().includes(filter.toLowerCase()));

  return (
    <div>
      <PageHeader
        title="Permissions & Access Control"
        subtitle="Decide who can see your folders and what they can do — nothing is shared until you grant it."
        actions={
          <button className="btn btn-primary" onClick={() => setShareOpen(true)}>
            <FolderPlus size={15} /> Share Folder
          </button>
        }
      />

      {error && tab !== "folders" && (
        <div className="card mb-4 px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div>
      )}

      <div className="mb-4 flex gap-1 rounded-lg bg-[var(--color-surface-2)] p-1 w-fit">
        <button className={`tab ${tab === "folders" ? "tab-active" : ""}`}
          onClick={() => setTab("folders")}>Shared Folders</button>
        <button className={`tab ${tab === "requests" ? "tab-active" : ""}`}
          onClick={() => setTab("requests")}>
          Access Requests
          {(requests?.incoming ?? []).some((r) => r.status === "pending") &&
            ` (${(requests?.incoming ?? []).filter((r) => r.status === "pending").length})`}
        </button>
        <button className={`tab ${tab === "blocked" ? "tab-active" : ""}`}
          onClick={() => setTab("blocked")}>Blocked Users</button>
      </div>

      {tab === "requests" && (
        <div className="max-w-2xl space-y-5">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-dim)]">
              Requests on your folders
            </div>
            {requests === null ? (
              <div className="py-8 text-center"><Spinner /></div>
            ) : requests.incoming.length === 0 ? (
              <EmptyState icon={<Inbox size={18} />} title="No requests"
                hint="When someone asks for more access to your folders it shows up here." />
            ) : (
              <div className="card divide-y divide-[var(--color-border)]">
                {requests.incoming.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-surface-3)] text-xs font-bold">
                      {initials(r.requester_email ?? r.requester_id)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm">
                        <span className="font-medium">{r.requester_email ?? r.requester_id.slice(0, 8)}</span>
                        <span className="text-[var(--color-text-dim)]"> requests </span>
                        <span className="font-medium capitalize">{r.role}</span>
                        <span className="text-[var(--color-text-dim)]"> access to </span>
                        <span className="font-medium">{r.folder_label}</span>
                      </div>
                      <div className="text-xs text-[var(--color-text-dim)]">
                        on {r.device_name} · {timeAgo(r.created_at)}
                      </div>
                    </div>
                    {r.status === "pending" ? (
                      <>
                        <select className="input !py-1 text-xs capitalize"
                          value={approveRole[r.id] ?? r.role}
                          onChange={(e) => setApproveRole({ ...approveRole, [r.id]: e.target.value })}>
                          {ROLES.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                        </select>
                        <button className="btn btn-primary !px-3 !py-1.5 text-xs"
                          onClick={() => resolveRequest(r.id, true)}>
                          <Check size={12} /> Approve
                        </button>
                        <button className="btn btn-ghost !px-3 !py-1.5 text-xs"
                          onClick={() => resolveRequest(r.id, false)}>Deny</button>
                      </>
                    ) : (
                      <span className={`badge ${r.status === "approved" ? "badge-green" : "badge-gray"} capitalize`}>
                        {r.status}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-dim)]">
              Requests you sent
            </div>
            {(requests?.outgoing ?? []).length === 0 ? (
              <p className="text-xs text-[var(--color-text-dim)]">
                You haven't requested access to anything — use "Request access"
                on a shared-with-you folder.
              </p>
            ) : (
              <div className="card divide-y divide-[var(--color-border)]">
                {(requests?.outgoing ?? []).map((r) => (
                  <div key={r.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm">
                        <span className="capitalize font-medium">{r.role}</span>
                        <span className="text-[var(--color-text-dim)]"> access to </span>
                        <span className="font-medium">{r.folder_label}</span>
                      </div>
                      <div className="text-xs text-[var(--color-text-dim)]">
                        on {r.device_name} · {timeAgo(r.created_at)}
                      </div>
                    </div>
                    <span className={`badge capitalize ${
                      r.status === "approved" ? "badge-green"
                        : r.status === "denied" ? "badge-red" : "badge-amber"}`}>
                      {r.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "blocked" && (
        <div className="max-w-xl">
          <div className="card p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Ban size={15} className="text-[var(--color-danger)]" /> Blocked users
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-dim)]">
              Blocked users lose every grant you've given them — their shares
              from you disappear until you unblock.
            </p>
            <div className="mt-3 flex gap-2">
              <input className="input flex-1" value={blockSubject}
                placeholder="Email, @handle, or user ID"
                onChange={(e) => setBlockSubject(e.target.value)} />
              <button className="btn btn-danger" disabled={busy || !blockSubject.trim()}
                onClick={blockUser}>Block</button>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            {(blocked ?? []).map((b) => (
              <div key={b.user_id} className="card flex items-center gap-3 px-4 py-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[rgba(248,113,113,0.15)] text-xs font-bold text-[var(--color-danger)]">
                  {initials(b.email ?? b.user_id)}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">{b.email ?? b.user_id}</span>
                <button className="btn btn-ghost !px-3 !py-1.5 text-xs"
                  onClick={() => unblockUser(b.user_id)}>Unblock</button>
              </div>
            ))}
            {blocked !== null && blocked.length === 0 && (
              <p className="py-4 text-center text-xs text-[var(--color-text-dim)]">
                Nobody blocked.
              </p>
            )}
          </div>
        </div>
      )}

      {tab === "folders" && (
      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        {/* left: shared folders */}
        <div>
          <div className="input mb-3 flex items-center gap-2 !py-2">
            <Search size={14} className="text-[var(--color-text-dim)]" />
            <input className="w-full bg-transparent text-sm outline-none"
              placeholder="Search folders…" value={filter}
              onChange={(e) => setFilter(e.target.value)} />
          </div>
          <div className="space-y-2">
            {filtered.map((s) => (
              <button key={s.id} onClick={() => setSelected(s)}
                className={`card w-full p-3 text-left transition-colors ${
                  selected?.id === s.id ? "border-[var(--color-primary)]" : "card-hover"
                }`}>
                <div className="flex items-center gap-2.5">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[rgba(251,191,36,0.12)]">
                    <FolderPlus size={15} className="text-[var(--color-warn)]" />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{s.label || basename(s.root_path)}</div>
                    <div className="truncate text-xs text-[var(--color-text-dim)]">{s.root_path}</div>
                  </div>
                </div>
              </button>
            ))}
            {filtered.length === 0 && (
              <EmptyState icon={<FolderPlus size={18} />} title="Nothing shared yet"
                hint="Share a folder from one of your computers, then grant access to colleagues." />
            )}
          </div>

          {granted.length > 0 && (
            <>
              <div className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-dim)]">
                Shared with you
              </div>
              <div className="space-y-2">
                {granted.map((s) => (
                  <div key={s.grant_id ?? s.id} className="card p-3">
                    <div className="truncate text-sm font-medium">{s.label || basename(s.root_path)}</div>
                    <div className="mt-0.5 flex items-center justify-between gap-2 text-xs text-[var(--color-text-dim)]">
                      <span className="truncate">
                        on {s.device_name} · <span className="capitalize">{bitsToRole(s.permissions ?? 0)}</span>
                      </span>
                      {(s.permissions ?? 0) < 255 && (
                        <button className="shrink-0 text-[var(--color-accent)] hover:underline"
                          onClick={() => requestUpgrade(s)}>
                          Request access
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* right: detail */}
        <div>
          {!selected ? (
            <EmptyState icon={<ShieldCheck size={20} />} title="Select a shared folder"
              hint="Pick a folder on the left to manage who has access." />
          ) : (
            <div className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">{selected.label || basename(selected.root_path)}</h2>
                  <div className="mt-0.5 text-xs text-[var(--color-text-dim)]">
                    {selected.root_path} · on {selected.device_name || "your device"}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="btn btn-primary" onClick={() => setAddOpen(true)}>
                    <UserPlus size={14} /> Add User
                  </button>
                  <button className="btn btn-danger" onClick={() => setConfirmStop(selected)}>
                    Stop Sharing
                  </button>
                </div>
              </div>

              <div className="mt-5 overflow-hidden rounded-lg border border-[var(--color-border)]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-[var(--color-surface-2)] text-left text-xs text-[var(--color-text-dim)]">
                      <th className="px-4 py-2.5 font-medium">User</th>
                      <th className="px-4 py-2.5 font-medium">Permission</th>
                      <th className="px-4 py-2.5 font-medium">Can do</th>
                      <th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {grants.map((g) => (
                      <tr key={g.id} className="border-t border-[var(--color-border)]">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2.5">
                            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-surface-3)] text-xs font-bold">
                              {initials(g.subject_user_id)}
                            </span>
                            <span className="font-mono text-xs">{g.subject_user_id.slice(0, 8)}…</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <select className="input !py-1 text-xs capitalize"
                            value={bitsToRole(g.permissions_granted)}
                            onChange={(e) => changeRole(g, e.target.value)}>
                            {ROLES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                          </select>
                        </td>
                        <td className="px-4 py-3"><PermBadges bits={g.permissions_granted} /></td>
                        <td className="px-4 py-3 text-right">
                          <button className="btn btn-ghost !p-2 text-[var(--color-danger)]"
                            title="Remove access" onClick={() => revokeGrant(g)}>
                            <X size={13} />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {grants.length === 0 && (
                      <tr><td colSpan={4} className="px-4 py-8 text-center text-xs text-[var(--color-text-dim)]">
                        Only you can see this folder — add a user to share it.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {addOpen && (
                <div className="fade-up mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
                  <div className="mb-3 text-sm font-medium">Grant access</div>
                  <input className="input w-full" value={subject} autoFocus
                    placeholder="Colleague's email, @handle, or user ID"
                    onChange={(e) => setSubject(e.target.value)} />
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {ROLES.map((r) => (
                      <button key={r.key} onClick={() => setRole(r.key)}
                        className={`rounded-lg border p-3 text-left transition-colors ${
                          role === r.key
                            ? "border-[var(--color-primary)] bg-[rgba(139,92,246,0.12)]"
                            : "border-[var(--color-border)] hover:border-[var(--color-accent)]"
                        }`}>
                        <r.icon size={15} className={role === r.key ? "text-[var(--color-accent)]" : "text-[var(--color-text-dim)]"} />
                        <div className="mt-1.5 text-sm font-semibold">{r.label}</div>
                        <div className="text-[11px] leading-snug text-[var(--color-text-dim)]">{r.desc}</div>
                      </button>
                    ))}
                  </div>
                  {error && <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>}
                  <div className="mt-4 flex justify-end gap-2">
                    <button className="btn btn-ghost" onClick={() => { setAddOpen(false); setError(null); }}>Cancel</button>
                    <button className="btn btn-primary" disabled={busy || !subject.trim()} onClick={addGrant}>
                      {busy ? <Spinner size={14} /> : <UserPlus size={14} />} Grant access
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      )}

      {/* share-folder modal: browse any folder OR file on your computer */}
      {shareOpen && (
        <Modal title="Share a folder or file" onClose={() => setShareOpen(false)} wide>
          <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Computer</label>
          <select className="input mb-3 w-full" value={pickDevice}
            onChange={(e) => {
              setPickDevice(e.target.value); setPickFolder(""); setPickAccess("read");
            }}>
            <option value="">Choose…</option>
            {devices.map((d) => (
              <option key={d.id} value={d.id}>{d.name} {d.status !== "online" ? "(offline)" : ""}</option>
            ))}
          </select>

          {pickDevice && (
            <PathBrowser key={pickDevice} deviceId={pickDevice} token={token!}
              selected={pickFolder} onPick={setPickFolder} />
          )}

          {pickFolder && (
            <div className="mt-3">
              <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Access level</label>
              <div className="grid grid-cols-2 gap-2">
                {(["read", "readwrite"] as const).map((a) => (
                  <button key={a} onClick={() => setPickAccess(a)}
                    className={`rounded-lg border p-2.5 text-left text-xs transition-colors ${
                      pickAccess === a
                        ? "border-[var(--color-primary)] bg-[rgba(139,92,246,0.12)]"
                        : "border-[var(--color-border)] hover:border-[var(--color-accent)]"
                    }`}>
                    <div className="font-semibold">{a === "read" ? "Read only" : "Read & write"}</div>
                    <div className="mt-0.5 text-[var(--color-text-dim)]">
                      {a === "read" ? "Browse + download only" : "Needed for uploads & sync"}
                    </div>
                  </button>
                ))}
              </div>
              <label className="mb-1 mt-3 block text-xs text-[var(--color-text-dim)]">Shown as</label>
              <input className="input w-full" placeholder="e.g. Project files"
                value={label} onChange={(e) => setLabel(e.target.value)} />
            </div>
          )}

          {error && <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>}
          <button className="btn btn-primary mt-4 w-full justify-center"
            disabled={!pickFolder || busy} onClick={createShare}>
            {busy ? <Spinner size={14} /> : <RefreshCw size={14} />}
            Share {pickFolder ? `“${basename(pickFolder)}”` : ""}
          </button>
        </Modal>
      )}

      {confirmStop && (
        <ConfirmDialog
          title="Stop sharing this folder?"
          body={`Everyone with access to “${confirmStop.label || confirmStop.root_path}” will lose it immediately.`}
          confirmLabel="Stop sharing" danger
          onConfirm={() => stopSharing(confirmStop)}
          onCancel={() => setConfirmStop(null)}
        />
      )}
    </div>
  );
}
