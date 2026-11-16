"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft, CloudOff, Download, FolderPlus, HardDrive, Pencil, Plus,
  Search, Tag, Trash2, Upload, X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useTransfers } from "@/components/TransferCenter";
import {
  ConfirmDialog, EmptyState, FileIcon, Modal, PageHeader, Spinner, StatusDot,
} from "@/components/ui";
import { basename, formatBytes, formatDate, parentPath } from "@/lib/format";
import type { Device, RemoteFileEntry, SharedFolder } from "@/types";

interface Root { path: string; label: string; access: string }

interface Picker {
  id: string;             // device id or `shared:<shareId>`
  label: string;
  deviceId: string;
  status: string;
  startPath: string;
  shared?: SharedFolder;
}

function filesFetch<T>(path: string, token: string, init?: RequestInit) {
  return apiFetch<T>(path, token, init);
}

function FilesInner() {
  const params = useSearchParams();
  const { token } = useAuth();
  const transfers = useTransfers();
  const [pickers, setPickers] = useState<Picker[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [roots, setRoots] = useState<Root[]>([]);
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<RemoteFileEntry[]>([]);
  const [tags, setTags] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  const [tagEdit, setTagEdit] = useState<RemoteFileEntry | null>(null);
  const [newTag, setNewTag] = useState("");
  const [renaming, setRenaming] = useState<RemoteFileEntry | null>(null);
  const [renameTo, setRenameTo] = useState("");
  const [mkdirOpen, setMkdirOpen] = useState(false);
  const [mkdirName, setMkdirName] = useState("");
  const [deleting, setDeleting] = useState<RemoteFileEntry | null>(null);
  const [uploading, setUploading] = useState(false);
  const uploadRef = useState<HTMLInputElement | null>(null);

  const picker = useMemo(
    () => pickers.find((p) => p.id === selected),
    [pickers, selected],
  );

  // ── loading ──

  const browse = useCallback(async (deviceId: string, p: string) => {
    setLoading(true); setError(null);
    try {
      const r = await filesFetch<{ entries: RemoteFileEntry[]; roots?: Root[] }>(
        `/api/v1/devices/${deviceId}/browse?path=${encodeURIComponent(p)}`, token!,
      );
      setEntries(r.entries);
      if (r.roots) setRoots(r.roots.map((x) => ({ ...x, label: x.label || basename(x.path) })));
      if (p) setPath(p);
      const t = await filesFetch<Record<string, string[]>>(
        `/api/v1/devices/${deviceId}/tags`, token!).catch(() => ({}));
      setTags(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "browse failed");
      setEntries([]);
    } finally { setLoading(false); }
  }, [token]);

  const search = useCallback(async (deviceId: string, q: string) => {
    setLoading(true); setError(null);
    try {
      const r = await filesFetch<{ results: RemoteFileEntry[] }>(
        `/api/v1/devices/${deviceId}/search?q=${encodeURIComponent(q)}`, token!,
      );
      setEntries(r.results);
    } catch (e) { setError(e instanceof Error ? e.message : "search failed"); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    (async () => {
      const [devs, shares] = await Promise.all([
        apiFetch<Device[]>("/api/v1/devices", token),
        apiFetch<{ granted: SharedFolder[] }>("/api/v1/sharing", token).catch(() => ({ owned: [], granted: [] })),
      ]);
      const list: Picker[] = [
        ...devs.filter((d) => !d.revoked_at).map((d) => ({
          id: d.id, label: d.name, deviceId: d.id, status: d.status, startPath: "",
        })),
        ...(shares.granted ?? []).map((s) => ({
          id: `shared:${s.id}`, label: `${s.label || basename(s.root_path)} — ${s.device_name}`,
          deviceId: s.device_id, status: "shared", startPath: s.root_path, shared: s,
        })),
      ];
      setPickers(list);
      const devParam = params.get("device");
      const pathParam = params.get("path");
      if (devParam) {
        const match = list.find((p) => p.deviceId === devParam);
        if (match) {
          setSelected(match.id);
          if (pathParam) browse(match.deviceId, pathParam);
          else browse(match.deviceId, match.startPath);
          return;
        }
      }
      const first = list.find((p) => p.status === "online") ?? list[0];
      if (first) { setSelected(first.id); browse(first.deviceId, first.startPath); }
    })();
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  function select(id: string) {
    setSelected(id);
    setEntries([]); setRoots([]); setPath(""); setSearchMode(false);
    const p = pickers.find((x) => x.id === id);
    if (p) browse(p.deviceId, p.startPath);
  }

  function open(e: RemoteFileEntry) {
    if (!e.is_dir || !picker) return;
    browse(picker.deviceId, e.path ?? e.rel_path);
  }

  function breadcrumbs(): { label: string; path: string }[] {
    if (!path || !picker) return [];
    const root = roots.find((r) => path.toLowerCase().startsWith(r.path.toLowerCase()));
    const base = root?.path ?? picker.startPath;
    if (!base) return [{ label: basename(path), path }];
    const out = [{ label: (root?.label ?? basename(base)) || "Folder", path: base }];
    const rel = path.slice(base.length).replace(/^[/\\]+/, "");
    let acc = base;
    for (const part of rel.split(/[/\\]/).filter(Boolean)) {
      acc = acc.replace(/[/\\]+$/, "") + "\\" + part;
      out.push({ label: part, path: acc });
    }
    return out;
  }

  // ── actions ──

  async function doRename() {
    if (!picker || !renaming) return;
    const e = renaming;
    await filesFetch(`/api/v1/devices/${picker.deviceId}/rename`, token!, {
      method: "POST",
      body: JSON.stringify({ path: e.path ?? e.rel_path, new_name: renameTo }),
    });
    setRenaming(null);
    searchMode ? search(picker.deviceId, searchQ) : browse(picker.deviceId, path);
  }

  async function doDelete() {
    if (!picker || !deleting) return;
    const e = deleting;
    await filesFetch(`/api/v1/devices/${picker.deviceId}/file?path=${encodeURIComponent(e.path ?? e.rel_path)}`,
      token!, { method: "DELETE" });
    setDeleting(null);
    searchMode ? search(picker.deviceId, searchQ) : browse(picker.deviceId, path);
  }

  async function doMkdir() {
    if (!picker || !mkdirName.trim()) return;
    await filesFetch(`/api/v1/devices/${picker.deviceId}/mkdir`, token!, {
      method: "POST", body: JSON.stringify({ path: path.replace(/[/\\]+$/, "") + "\\" + mkdirName.trim() }),
    });
    setMkdirOpen(false); setMkdirName("");
    browse(picker.deviceId, path);
  }

  async function doUpload(fileList: FileList | null) {
    if (!picker || !fileList?.length || !token) return;
    setUploading(true);
    const base = process.env.NEXT_PUBLIC_CLOUD_API_URL ?? "http://localhost:8000";
    try {
      for (const f of Array.from(fileList)) {
        const t = transfers.begin(f.name, f.size, "up");
        await new Promise<void>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open("POST",
            `${base}/api/v1/devices/${picker.deviceId}/upload?path=${encodeURIComponent(path)}`);
          xhr.setRequestHeader("Authorization", `Bearer ${token}`);
          xhr.upload.onprogress = (ev) => transfers.progress(t.id, ev.loaded);
          xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload failed (${xhr.status})`)));
          xhr.onerror = () => reject(new Error("upload failed"));
          const abort = () => { xhr.abort(); reject(new DOMException("aborted", "AbortError")); };
          t.signal.addEventListener("abort", abort, { once: true });
          const fd = new FormData();
          fd.append("file", f, f.name);
          xhr.send(fd);
        }).then(() => transfers.finish(t.id))
          .catch((err) => { if (!t.signal.aborted) transfers.fail(t.id, err instanceof Error ? err.message : "failed"); });
      }
      browse(picker.deviceId, path);
    } finally { setUploading(false); }
  }

  async function download(e: RemoteFileEntry) {
    if (!picker || !token) return;
    const base = process.env.NEXT_PUBLIC_CLOUD_API_URL ?? "http://localhost:8000";
    const t = transfers.begin(e.name, e.size ?? 0, "down");
    try {
      const res = await fetch(
        `${base}/api/v1/devices/${picker.deviceId}/download?path=${encodeURIComponent(e.path ?? e.rel_path)}`,
        { headers: { Authorization: `Bearer ${token}` }, signal: t.signal },
      );
      if (!res.ok || !res.body) throw new Error(`download failed (${res.status})`);
      const reader = res.body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        transfers.progress(t.id, received);
      }
      const url = URL.createObjectURL(new Blob(chunks as BlobPart[]));
      const a = document.createElement("a");
      a.href = url; a.download = e.name; a.click();
      URL.revokeObjectURL(url);
      transfers.finish(t.id);
    } catch (err) {
      if (t.signal.aborted) return; // row already marked cancelled
      transfers.fail(t.id, err instanceof Error ? err.message : "download failed");
    }
  }

  async function saveTag() {
    if (!picker || !tagEdit || !newTag.trim()) return;
    const p = tagEdit.path ?? tagEdit.rel_path;
    await filesFetch(`/api/v1/devices/${picker.deviceId}/tags`, token!, {
      method: "PUT", body: JSON.stringify({ path: p, tag: newTag.trim() }),
    });
    setTags((t) => ({ ...t, [p]: [...new Set([...(t[p] ?? []), newTag.trim()])] }));
    setNewTag(""); setTagEdit(null);
  }

  async function removeTag(p: string, tag: string) {
    if (!picker) return;
    await filesFetch(`/api/v1/devices/${picker.deviceId}/tags?path=${encodeURIComponent(p)}&tag=${encodeURIComponent(tag)}`,
      token!, { method: "DELETE" });
    setTags((t) => ({ ...t, [p]: (t[p] ?? []).filter((x) => x !== tag) }));
  }

  const currentRoot = roots.find((r) => path.toLowerCase().startsWith(r.path.toLowerCase()));
  const canWrite = !picker?.shared
    ? currentRoot?.access === "readwrite"
    : (picker.shared.permissions ?? 0) & 4;

  return (
    <div>
      <PageHeader title="Files"
        subtitle={picker ? `${picker.label}${picker.shared ? " · shared with you" : ""}` : "Browse, download and organize files on connected computers."}
        actions={
          <>
            <select className="input" value={selected} onChange={(e) => select(e.target.value)}>
              {pickers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}{p.status === "offline" ? " (offline)" : p.shared ? " (shared)" : ""}
                </option>
              ))}
            </select>
            {canWrite && (
              <>
                <button className="btn btn-ghost" onClick={() => setMkdirOpen(true)}>
                  <FolderPlus size={14} /> New folder
                </button>
                <label className="btn btn-primary cursor-pointer">
                  {uploading ? <Spinner size={14} /> : <Upload size={14} />} Upload
                  <input type="file" multiple className="hidden"
                    ref={(el) => uploadRef[1](el)}
                    onChange={(e) => { doUpload(e.target.files); e.target.value = ""; }} />
                </label>
              </>
            )}
          </>
        }
      />

      {/* toolbar: breadcrumbs + search */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {searchMode ? (
          <button className="btn btn-ghost !p-2" onClick={() => { setSearchMode(false); browse(picker!.deviceId, path); }}>
            <ArrowLeft size={15} />
          </button>
        ) : (
          <nav className="flex min-w-0 flex-wrap items-center gap-1 text-sm">
            {!path && <span className="text-[var(--color-text-dim)]">All shared folders</span>}
            {breadcrumbs().map((b, i, arr) => (
              <span key={b.path} className="flex items-center gap-1">
                {i > 0 && <span className="text-[var(--color-text-dim)]">/</span>}
                <button
                  className={i === arr.length - 1 ? "font-medium" : "text-[var(--color-text-dim)] hover:text-[var(--color-accent)]"}
                  onClick={() => picker && browse(picker.deviceId, b.path)}>
                  {b.label}
                </button>
              </span>
            ))}
            {path && parentPath(path) && (
              <button className="btn btn-ghost ml-2 !p-1.5" title="Up"
                onClick={() => picker && browse(picker.deviceId, parentPath(path)!)}>
                <ArrowLeft size={13} />
              </button>
            )}
          </nav>
        )}
        <form className="input flex min-w-[240px] flex-1 items-center gap-2 !py-1.5"
          onSubmit={(e) => { e.preventDefault(); if (searchQ.trim() && picker) { setSearchMode(true); search(picker.deviceId, searchQ); } }}>
          <Search size={14} className="text-[var(--color-text-dim)]" />
          <input className="w-full bg-transparent text-sm outline-none"
            placeholder={`Search on ${picker?.label ?? "device"}…`}
            value={searchQ} onChange={(e) => setSearchQ(e.target.value)} />
        </form>
      </div>

      {error && (
        <div className="card mb-4 flex items-center gap-2 px-4 py-3 text-sm text-[var(--color-danger)]">
          <CloudOff size={15} /> {error}
        </div>
      )}

      {/* two-pane: folder tree + entries */}
      <div className="grid gap-4 lg:grid-cols-[230px_1fr]">
        <div className="card hidden self-start p-2 lg:block">
          <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
            Shared folders
          </div>
          {roots.map((r) => (
            <button key={r.path}
              className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm ${
                path.toLowerCase().startsWith(r.path.toLowerCase())
                  ? "bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)]"
                  : "hover:bg-[var(--color-surface-2)]"
              }`}
              onClick={() => picker && browse(picker.deviceId, r.path)}>
              <HardDrive size={14} className="shrink-0" />
              <span className="truncate">{r.label}</span>
            </button>
          ))}
          {roots.length === 0 && (
            <div className="px-2.5 py-3 text-xs text-[var(--color-text-dim)]">
              No shared folders — add them under Devices → Folders.
            </div>
          )}
        </div>

        <div className="card overflow-hidden">
        {loading ? (
          <div className="p-10 text-center"><Spinner /></div>
        ) : entries.length === 0 ? (
          <div className="p-10 text-center text-sm text-[var(--color-text-dim)]">
            {searchMode ? "No matches." : path ? "Empty folder." :
              picker?.shared ? "" : "No shared folders yet — add one under Devices → Folders."}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-surface-2)] text-left text-xs text-[var(--color-text-dim)]">
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Tags</th>
                <th className="px-4 py-2.5 font-medium">Size</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Modified</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const p = e.path ?? e.rel_path;
                const t = tags[p] ?? [];
                const dir = !!e.is_dir;
                return (
                  <tr key={p} className="group border-t border-[var(--color-border)] hover:bg-[var(--color-surface-2)]">
                    <td className="px-4 py-2.5">
                      <button className="flex items-center gap-2.5 text-left"
                        onClick={() => dir ? open(e) : download(e)} disabled={!dir && false}>
                        <FileIcon name={e.name} isDir={dir} />
                        <span className="truncate">{e.name}</span>
                      </button>
                    </td>
                    <td className="hidden px-4 py-2.5 md:table-cell">
                      <div className="flex flex-wrap items-center gap-1">
                        {t.map((tag) => (
                          <button key={tag} className="chip" title="Remove tag"
                            onClick={() => removeTag(p, tag)}>
                            <Tag size={9} /> {tag} <X size={9} />
                          </button>
                        ))}
                        <button className="chip opacity-0 transition-opacity group-hover:opacity-100"
                          title="Add tag" onClick={() => { setTagEdit(e); setNewTag(""); }}>
                          <Plus size={10} /> tag
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-[var(--color-text-dim)]">
                      {dir ? "—" : formatBytes(e.size ?? 0)}
                    </td>
                    <td className="hidden px-4 py-2.5 text-xs text-[var(--color-text-dim)] md:table-cell">
                      {formatDate(e.mtime)}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="relative flex justify-end">
                        <button className="btn btn-ghost !p-1.5 opacity-0 transition-opacity group-hover:opacity-100"
                          onClick={() => setMenu(menu === p ? null : p)}>···</button>
                        {menu === p && (
                          <div className="card absolute right-0 top-full z-20 mt-1 w-40 p-1.5">
                            {!dir && (
                              <button className="menu-item" onClick={() => { download(e); setMenu(null); }}>
                                <Download size={13} /> Download
                              </button>
                            )}
                            <button className="menu-item" onClick={() => { setTagEdit(e); setMenu(null); }}>
                              <Tag size={13} /> Add tag
                            </button>
                            {canWrite && (
                              <>
                                <button className="menu-item" onClick={() => { setRenaming(e); setRenameTo(e.name); setMenu(null); }}>
                                  <Pencil size={13} /> Rename
                                </button>
                                <button className="menu-item text-[var(--color-danger)]" onClick={() => { setDeleting(e); setMenu(null); }}>
                                  <Trash2 size={13} /> Delete
                                </button>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        </div>
      </div>
      {!path && !searchMode && roots.length > 0 && (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {roots.map((r) => (
            <button key={r.path} className="card card-hover flex items-center gap-3 p-3 text-left"
              onClick={() => picker && browse(picker.deviceId, r.path)}>
              <HardDrive size={16} className="text-[var(--color-accent)]" />
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{r.label}</div>
                <div className="truncate text-xs text-[var(--color-text-dim)]">
                  {r.path} · {(r.access === "granted" ? "shared" : r.access) ?? ""}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* dialogs */}
      {tagEdit && (
        <Modal title="Add tag" onClose={() => setTagEdit(null)}>
          <p className="mb-3 truncate text-xs text-[var(--color-text-dim)]">{tagEdit.name}</p>
          <div className="flex gap-2">
            <input className="input flex-1" autoFocus placeholder="e.g. urgent, fyp, client-a"
              value={newTag} onChange={(e) => setNewTag(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveTag()} />
            <button className="btn btn-primary" onClick={saveTag} disabled={!newTag.trim()}>Add</button>
          </div>
        </Modal>
      )}
      {renaming && (
        <Modal title="Rename" onClose={() => setRenaming(null)}>
          <p className="mb-3 truncate text-xs text-[var(--color-text-dim)]">{renaming.name}</p>
          <div className="flex gap-2">
            <input className="input flex-1" autoFocus value={renameTo}
              onChange={(e) => setRenameTo(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doRename()} />
            <button className="btn btn-primary" onClick={doRename} disabled={!renameTo.trim()}>Rename</button>
          </div>
        </Modal>
      )}
      {mkdirOpen && (
        <Modal title="New folder" onClose={() => setMkdirOpen(false)}>
          <div className="flex gap-2">
            <input className="input flex-1" autoFocus placeholder="Folder name"
              value={mkdirName} onChange={(e) => setMkdirName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doMkdir()} />
            <button className="btn btn-primary" onClick={doMkdir} disabled={!mkdirName.trim()}>Create</button>
          </div>
        </Modal>
      )}
      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.name}?`}
          body="This permanently deletes the file on that computer — it is not moved to the recycle bin."
          confirmLabel="Delete" danger
          onConfirm={doDelete} onCancel={() => setDeleting(null)}
        />
      )}
      <style jsx global>{`
        .menu-item { display: flex; align-items: center; gap: 0.5rem; width: 100%;
          border-radius: 0.4rem; padding: 0.4rem 0.6rem; font-size: 0.8rem; text-align: left; }
        .menu-item:hover { background: var(--color-surface-2); }
      `}</style>
    </div>
  );
}

export default function FilesPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center"><Spinner /></div>}>
      <FilesInner />
    </Suspense>
  );
}
