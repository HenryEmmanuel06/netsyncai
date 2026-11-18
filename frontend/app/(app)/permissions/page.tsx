"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Ban, Check, Eye, FileText, Folder, FolderPlus, Inbox, Lock, Pencil,
  Search, ShieldCheck, UserPlus, X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import {
  ConfirmDialog, Dropdown, EmptyState, FolderArt, Modal, PageHeader,
  PermBadges, Spinner,
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

/** A folder shared on one of your devices (via the Devices page), merged
 *  with its backend share record when one exists. Share records are what
 *  grants attach to — a root without one gets it lazily on first grant. */
interface PermFolder {
  key: string;
  deviceId: string;
  deviceName: string;
  path: string;
  label: string;
  access?: string;          // undefined = can't verify (device offline)
  indexing?: boolean;
  index_done?: number;
  index_total?: number;
  share?: SharedFolder;
}

const normPath = (p: string) =>
  p.replace(/\//g, "\\").replace(/\\+$/, "").toLowerCase();

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

const FILE_ROOT_RE = /\.[A-Za-z0-9]{1,8}$/;

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
  const [roots, setRoots] = useState<Record<string, SharedFolderInfo[] | null>>({});
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [sharedSel, setSharedSel] = useState<SharedFolder | null>(null);
  const [grants, setGrants] = useState<GrantEntry[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [subject, setSubject] = useState("");
  const [role, setRole] = useState<string>("viewer");
  const [shareOpen, setShareOpen] = useState(false);
  const [pickDevice, setPickDevice] = useState("");
  const [modalRoots, setModalRoots] = useState<SharedFolderInfo[] | null>(null);
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
    const active = devs.filter((d) => !d.revoked_at);
    setDevices(active);
    setOwned(shares.owned);
    setGranted(shares.granted);
    setRoots(Object.fromEntries(await Promise.all(active.map(async (d) => {
      try {
        const r = await apiFetch<{ folders: SharedFolderInfo[] }>(
          `/api/v1/devices/${d.id}/folders`, token);
        return [d.id, r.folders ?? []] as const;
      } catch {
        return [d.id, null] as const;   // offline — roots can't be verified
      }
    }))));
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

  /** Folders the user shared on their devices, merged with share records. */
  const folders = useMemo<PermFolder[]>(() => {
    const out: PermFolder[] = [];
    const matched = new Set<string>();
    for (const d of devices) {
      for (const r of roots[d.id] ?? []) {
        const share = owned.find(
          (s) => s.device_id === d.id && normPath(s.root_path) === normPath(r.path));
        if (share) matched.add(share.id);
        out.push({
          key: `f:${d.id}:${normPath(r.path)}`,
          deviceId: d.id, deviceName: d.name, path: r.path,
          label: r.label || basename(r.path),
          access: r.access, indexing: r.indexing,
          index_done: r.index_done, index_total: r.index_total, share,
        });
      }
    }
    // Share records we can't verify (device offline) still show so grants
    // stay manageable; shares of deleted/revoked devices drop out.
    for (const s of owned) {
      if (matched.has(s.id) || !(s.device_id in roots)) continue;
      out.push({
        key: `s:${s.id}`, deviceId: s.device_id,
        deviceName: s.device_name || "your device",
        path: s.root_path, label: s.label || basename(s.root_path), share: s,
      });
    }
    return out;
  }, [devices, roots, owned]);

  const selected = folders.find((f) => f.key === selectedKey) ?? null;
  const selectedReadOnly = selected?.access === "read";
  // the share whose grants are being managed — own selection, or a
  // shared-with-me folder where we hold Manager bits (delegated granting)
  const sharedIsManager = !!(sharedSel?.permissions && sharedSel.permissions & 1024);
  const activeShare = selected?.share ?? (sharedIsManager ? sharedSel : null);
  const detailShareId = activeShare?.id;

  useEffect(() => {
    if (!detailShareId || !token) { setGrants([]); return; }
    apiFetch<GrantEntry[]>(`/api/v1/sharing/${detailShareId}/grants`, token)
      .then(setGrants).catch(() => setGrants([]));
  }, [detailShareId, token]);

  // modal: folders shared on the picked device (fresh fetch when it changes)
  useEffect(() => {
    if (!pickDevice || !token) { setModalRoots(null); return; }
    let live = true;
    setModalRoots(null);
    apiFetch<{ folders: SharedFolderInfo[] }>(
      `/api/v1/devices/${pickDevice}/folders`, token)
      .then((r) => { if (live) setModalRoots(r.folders ?? []); })
      .catch(() => { if (live) setModalRoots([]); });
    return () => { live = false; };
  }, [pickDevice, token]);

  /** Pick a device-shared folder: create its share record (if needed) and
   *  select it so the owner can grant colleagues access. */
  async function shareRoot(r: SharedFolderInfo, existing?: SharedFolder) {
    setBusy(true); setError(null);
    try {
      if (!existing) {
        await apiFetch("/api/v1/sharing", token!, {
          method: "POST",
          body: JSON.stringify({
            device_id: pickDevice, root_path: r.path,
            label: r.label || basename(r.path),
          }),
        });
      }
      await load();
      setShareOpen(false); setPickDevice("");
      setSelectedKey(`f:${pickDevice}:${normPath(r.path)}`);
    } catch (e) { setError(e instanceof Error ? e.message : "could not share"); }
    finally { setBusy(false); }
  }

  async function addGrant() {
    if (!activeShare || !subject.trim()) return;
    const bits = ROLES.find((r) => r.key === role)!.bits;
    if (selectedReadOnly && bits & ~3) {
      setError(`"${selected!.label}" was shared with read-only access — switch it to read & write on the Devices page before granting Editor or Manager.`);
      return;
    }
    setBusy(true); setError(null);
    try {
      let share = activeShare;
      if (selected && !share) {
        // no share record yet → create it so grants have something to attach to
        share = await apiFetch<SharedFolder>("/api/v1/sharing", token!, {
          method: "POST",
          body: JSON.stringify({
            device_id: selected.deviceId, root_path: selected.path,
            label: selected.label,
          }),
        });
      }
      await apiFetch(`/api/v1/sharing/${share.id}/grants`, token!, {
        method: "POST",
        body: JSON.stringify({ subject: subject.trim(), permissions: bits }),
      });
      setSubject(""); setAddOpen(false); setRole("viewer");
      await load();
      const g = await apiFetch<GrantEntry[]>(`/api/v1/sharing/${share.id}/grants`, token!);
      setGrants(g);
    } catch (e) { setError(e instanceof Error ? e.message : "grant failed"); }
    finally { setBusy(false); }
  }

  async function changeRole(g: GrantEntry, next: string) {
    if (!activeShare) return;
    const shareId = activeShare.id;
    const bits = ROLES.find((r) => r.key === next)!.bits;
    if (selectedReadOnly && bits & ~3) return;
    setError(null);
    await apiFetch(`/api/v1/sharing/${shareId}/grants/${g.id}`, token!, { method: "DELETE" });
    try {
      await apiFetch(`/api/v1/sharing/${shareId}/grants`, token!, {
        method: "POST",
        body: JSON.stringify({ subject: g.subject_user_id, permissions: bits }),
      });
    } catch (e) {
      // restore the old role so a rejected change doesn't strip access
      await apiFetch(`/api/v1/sharing/${shareId}/grants`, token!, {
        method: "POST",
        body: JSON.stringify({ subject: g.subject_user_id, permissions: g.permissions_granted }),
      }).catch(() => {});
      setError(e instanceof Error ? e.message : "could not change role");
    }
    const g2 = await apiFetch<GrantEntry[]>(`/api/v1/sharing/${shareId}/grants`, token!)
      .catch(() => []);
    setGrants(g2);
  }

  async function revokeGrant(g: GrantEntry) {
    if (!activeShare) return;
    await apiFetch(`/api/v1/sharing/${activeShare.id}/grants/${g.id}`, token!, { method: "DELETE" });
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

  async function upgradeAccess() {
    if (!selected) return;
    setBusy(true); setError(null);
    try {
      await apiFetch(`/api/v1/devices/${selected.deviceId}/folders`, token!, {
        method: "PATCH",
        body: JSON.stringify({ path: selected.path, access: "readwrite" }),
      });
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "could not change access"); }
    finally { setBusy(false); }
  }

  async function stopSharing(s: SharedFolder) {
    setConfirmStop(null);
    await apiFetch(`/api/v1/sharing/${s.id}`, token!, { method: "DELETE" });
    await load();
  }

  const filtered = folders.filter((f) =>
    (f.label + f.path).toLowerCase().includes(filter.toLowerCase()));

  return (
    <div>
      <PageHeader
        title="Permissions & Access Control"
        subtitle="Decide who can see your folders and what they can do — nothing is shared until you grant it."
        actions={
          <button className="btn btn-primary"
            onClick={() => { setPickDevice(devices[0]?.id ?? ""); setShareOpen(true); }}>
            <FolderPlus size={15} /> Share Folder
          </button>
        }
      />

      {error && !addOpen && !shareOpen && (
        <div className="card mb-4 px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div>
      )}

      <div className="segmented mb-5">
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
                {requests.incoming.map((r) => {
                  const reqReadOnly = folders.find(
                    (f) => f.share?.id === r.folder_id)?.access === "read";
                  return (
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
                        <Dropdown className="w-36 text-xs"
                          value={reqReadOnly ? "viewer" : approveRole[r.id] ?? r.role}
                          onChange={(v) => setApproveRole({ ...approveRole, [r.id]: v })}
                          options={ROLES.map((x) => ({
                            value: x.key, label: x.label,
                            disabled: reqReadOnly && x.key !== "viewer",
                          }))} />
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
                  );
                })}
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
      <div>
        {/* shared folders — card grid */}
        <div className="input mb-4 flex max-w-md items-center gap-2 !py-2">
          <Search size={14} className="text-[var(--color-text-dim)]" />
          <input className="w-full bg-transparent text-sm outline-none"
            placeholder="Search folders…" value={filter}
            onChange={(e) => setFilter(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
          {filtered.map((f) => (
            <button key={f.key}
              onClick={() => { setSelectedKey(f.key); setSharedSel(null); setAddOpen(false); setError(null); }}
              className={`card p-4 text-left transition-colors ${
                selected?.key === f.key
                  ? "border-[var(--color-primary)] ring-1 ring-[var(--color-primary)]"
                  : "card-hover"
              }`}>
              <div className="flex flex-col items-center pt-1 text-center">
                <FolderArt size={56} />
                <div className="mt-2.5 w-full truncate text-sm font-semibold">{f.label}</div>
                <span className="pill mt-1">{f.deviceName}</span>
              </div>
              <div className="mt-3 space-y-1 border-t border-[var(--color-border)] pt-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[var(--color-text-dim)]">Owner</span>
                  <span className="font-medium">You</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[var(--color-text-dim)]">Access</span>
                  <span className={`font-medium ${
                    f.access === "readwrite" ? "text-[var(--color-accent)]"
                    : f.access === "read" ? "text-[var(--color-text)]"
                    : "text-[var(--color-warn)]"}`}>
                    {f.access === "readwrite" ? "Full" : f.access === "read" ? "View only" : "Offline"}
                  </span>
                </div>
                {f.indexing && (
                  <div className="flex items-center justify-between">
                    <span className="text-[var(--color-text-dim)]">Indexing</span>
                    <span className="font-medium text-[var(--color-warn)]">
                      {f.index_total
                        ? `${Math.round(((f.index_done ?? 0) / f.index_total) * 100)}%`
                        : `${f.index_done ?? 0} files`}
                    </span>
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
        {filtered.length === 0 && (
          <EmptyState icon={<FolderPlus size={18} />} title="Nothing shared yet"
            hint="Share a folder from the Devices page (or the button above), then grant colleagues access here." />
        )}

        {/* shared with you — purple cards */}
        {granted.length > 0 && (
          <>
            <div className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-dim)]">
              Shared with you
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
              {granted.map((s) => (
                <button key={s.grant_id ?? s.id}
                  onClick={() => { setSharedSel(s); setSelectedKey(null); setAddOpen(false); setSubject(""); setError(null); }}
                  className={`card p-4 text-left transition-colors ${
                    sharedSel?.id === s.id
                      ? "border-[var(--color-primary)] ring-1 ring-[var(--color-primary)]"
                      : "card-hover"
                  }`}>
                  <div className="flex flex-col items-center pt-1 text-center">
                    <FolderArt size={56} tone="purple" />
                    <div className="mt-2.5 w-full truncate text-sm font-semibold">
                      {s.label || basename(s.root_path)}
                    </div>
                    <span className="pill mt-1">{s.device_name}</span>
                  </div>
                  <div className="mt-3 space-y-1 border-t border-[var(--color-border)] pt-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[var(--color-text-dim)]">Owner</span>
                      <span className="truncate font-medium">{s.owner_email ?? s.device_name}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[var(--color-text-dim)]">Your access</span>
                      <span className="font-medium capitalize text-[var(--color-accent)]">
                        {bitsToRole(s.permissions ?? 0)}
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      )}

      {/* folder detail modal — owned shares, or shared-with-me folders
          where we hold Manager access and can delegate further */}
      {(selected || sharedSel) && (
        <Modal title={selected?.label ?? (sharedSel!.label || basename(sharedSel!.root_path))}
          subtitle={selected
            ? `${selected.path} · on ${selected.deviceName}`
            : `on ${sharedSel!.device_name} · shared by ${sharedSel!.owner_email ?? "the owner"}`}
          icon={<ShieldCheck size={16} className="text-[var(--color-accent)]" />}
          onClose={() => { setSelectedKey(null); setSharedSel(null); setAddOpen(false); setSubject(""); setError(null); }}
          wide>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {selected && (
                selected.access === "readwrite" ? (
                  <span className="badge badge-purple">Full access on device</span>
                ) : selected.access === "read" ? (
                  <>
                    <span className="badge badge-gray">Read-only on device</span>
                    <button className="text-[11px] text-[var(--color-accent)] hover:underline"
                      disabled={busy} onClick={upgradeAccess}>
                      Switch to Full access
                    </button>
                  </>
                ) : (
                  <span className="badge badge-amber">Device offline — access unverified</span>
                )
              )}
              {sharedSel && (
                <>
                  <span className="badge badge-purple capitalize">
                    {bitsToRole(sharedSel.permissions ?? 0)}
                  </span>
                  {!sharedIsManager && (
                    <span className="text-[11px] text-[var(--color-text-dim)]">
                      Only the owner and managers can invite others.
                    </span>
                  )}
                </>
              )}
            </div>
            <div className="flex gap-2">
              {sharedSel && (sharedSel.permissions ?? 0) < 255 && !sharedIsManager && (
                <button className="btn btn-ghost" onClick={() => requestUpgrade(sharedSel)}>
                  Request access
                </button>
              )}
              {sharedSel && sharedIsManager && (
                <span className="text-[11px] text-[var(--color-text-faint)]">
                  Delegating — the owner stays in control
                </span>
              )}
              {(selected || sharedIsManager) && (
                <button className="btn btn-primary"
                  onClick={() => { setAddOpen((o) => !o); setRole("viewer"); setError(null); }}>
                  <UserPlus size={14} /> Add User
                </button>
              )}
              {selected?.share && (
                <button className="btn btn-danger" onClick={() => setConfirmStop(selected.share!)}>
                  Stop Sharing
                </button>
              )}
            </div>
          </div>

          {(selected || sharedIsManager) && (
            <div className="mt-4 overflow-hidden rounded-lg border border-[var(--color-border)]">
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
                        <Dropdown className="w-36 text-xs"
                          value={bitsToRole(g.permissions_granted)}
                          onChange={(v) => changeRole(g, v)}
                          options={ROLES.map((r) => ({
                            value: r.key, label: r.label,
                            disabled: (selectedReadOnly && r.key !== "viewer")
                              || (sharedIsManager && r.key === "manager"),
                          }))} />
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
                      {selected ? "Only you can see this folder — add a user to share it."
                                : "No one else has access yet — invite someone."}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {addOpen && (selected || sharedIsManager) && (
            <div className="fade-up mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
              <div className="mb-3 text-sm font-medium">Grant access</div>
              <input className="input w-full" value={subject} autoFocus
                placeholder="Colleague's email, @handle, or user ID"
                onChange={(e) => setSubject(e.target.value)} />
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {ROLES.map((r) => {
                  const locked = (selectedReadOnly && r.key !== "viewer")
                    || (sharedIsManager && r.key === "manager");
                  return (
                    <button key={r.key} disabled={locked} onClick={() => setRole(r.key)}
                      className={`rounded-lg border p-3 text-left transition-colors ${
                        role === r.key && !locked
                          ? "border-[var(--color-primary)] bg-[rgba(139,92,246,0.12)]"
                          : "border-[var(--color-border)] hover:border-[var(--color-accent)]"
                      } ${locked ? "cursor-not-allowed opacity-45" : ""}`}>
                      <div className="flex items-center justify-between">
                        <r.icon size={15}
                          className={role === r.key && !locked ? "text-[var(--color-accent)]" : "text-[var(--color-text-dim)]"} />
                        {locked && <Lock size={11} className="text-[var(--color-text-faint)]" />}
                      </div>
                      <div className="mt-1.5 text-sm font-semibold">{r.label}</div>
                      <div className="text-[11px] leading-snug text-[var(--color-text-dim)]">
                        {locked && sharedIsManager ? "Only the owner can grant Manager"
                          : locked ? "Needs read & write on the device" : r.desc}
                      </div>
                    </button>
                  );
                })}
              </div>
              {selectedReadOnly && selected && (
                <p className="mt-2 text-[11px] leading-snug text-[var(--color-text-dim)]">
                  “{selected.label}” was shared with read-only access on {selected.deviceName} —
                  switch it to read &amp; write on the Devices page to grant Editor or Manager.
                </p>
              )}
              {error && <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>}
              <div className="mt-4 flex justify-end gap-2">
                <button className="btn btn-ghost" onClick={() => { setAddOpen(false); setError(null); }}>Cancel</button>
                <button className="btn btn-primary" disabled={busy || !subject.trim()} onClick={addGrant}>
                  {busy ? <Spinner size={14} /> : <UserPlus size={14} />} Grant access
                </button>
              </div>
            </div>
          )}
        </Modal>
      )}

      {/* share modal: pick a folder already shared on the device */}
      {shareOpen && (
        <Modal title="Share a folder or file"
          subtitle="Pick one of the folders shared on this computer — add new ones from the Devices page."
          onClose={() => setShareOpen(false)} wide>
          <label className="mb-1 block text-xs text-[var(--color-text-dim)]">Computer</label>
          <Dropdown className="mb-3 w-full" value={pickDevice}
            placeholder="Choose…"
            onChange={(v) => setPickDevice(v)}
            options={devices.map((d) => ({
              value: d.id, label: d.name,
              hint: d.status !== "online" ? "offline" : "online",
            }))} />

          {pickDevice && (
            <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
              <div className="border-b border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-text-dim)]">
                Folders shared on this device
              </div>
              <div className="max-h-64 overflow-y-auto p-1">
                {modalRoots === null ? (
                  <div className="py-8 text-center"><Spinner /></div>
                ) : modalRoots.length === 0 ? (
                  <div className="py-8 text-center text-xs leading-relaxed text-[var(--color-text-dim)]">
                    Nothing shared on this computer yet —<br />
                    share a folder or file from the Devices page first.
                  </div>
                ) : (
                  modalRoots.map((r) => {
                    const existing = owned.find(
                      (s) => s.device_id === pickDevice
                        && normPath(s.root_path) === normPath(r.path));
                    return (
                      <button key={r.path} disabled={busy}
                        className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-[var(--color-surface-2)] disabled:opacity-60"
                        onClick={() => shareRoot(r, existing)}>
                        {FILE_ROOT_RE.test(r.label || r.path)
                          ? <FileText size={14} className="shrink-0 text-[var(--color-text-dim)]" />
                          : <Folder size={14} className="shrink-0 text-[var(--color-warn)]" />}
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {r.label || basename(r.path)}
                          </span>
                          <span className="block truncate text-[11px] text-[var(--color-text-dim)]">
                            {r.path}
                          </span>
                        </span>
                        {existing ? (
                          <span className="badge badge-purple shrink-0">Already sharing</span>
                        ) : (
                          <span className="badge badge-gray shrink-0">
                            {r.access === "readwrite" ? "Full access" : "View only"}
                          </span>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {error && <p className="mt-2 text-xs text-[var(--color-danger)]">{error}</p>}
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
