"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft, Check, ChevronDown, ChevronRight, CloudOff, Download, Eye, FileText, Folder,
  FolderPlus, FolderX, HardDrive, LayoutGrid, List, Monitor, Pencil, Plus,
  Search, Tag, Trash2, Upload, X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { useTransfers } from "@/components/TransferCenter";
import {
  ConfirmDialog, Dropdown, EmptyState, FileIcon, FolderArt, Modal, PageHeader, Spinner, StatusDot,
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

const ACCESS_META: Record<string, { label: string; desc: string }> = {
  read: { label: "View only", desc: "Colleagues can browse and download" },
  readwrite: { label: "Full access", desc: "Colleagues can also add, rename and delete" },
  granted: { label: "Shared with you", desc: "" },
};

const FILE_ROOT_RE = /\.[A-Za-z0-9]{1,8}$/;

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
  const [notice, setNotice] = useState<string | null>(null);
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
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [treeRoots, setTreeRoots] = useState<Record<string, Root[]>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [accessMenu, setAccessMenu] = useState<string | null>(null);
  const [unshare, setUnshare] = useState<Root | null>(null);

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

  async function setAccess(r: Root, access: "read" | "readwrite") {
    setAccessMenu(null);
    if (!picker || access === r.access) return;
    setError(null); setNotice(null);
    try {
      await filesFetch(`/api/v1/devices/${picker.deviceId}/folders`, token!, {
        method: "PATCH", body: JSON.stringify({ path: r.path, access }),
      });
      const upd = (rs: Root[]) => rs.map((x) => (x.path === r.path ? { ...x, access } : x));
      setRoots(upd);
      setTreeRoots((t) => ({ ...t, [picker.deviceId]: upd(t[picker.deviceId] ?? []) }));
      setNotice(`${r.label} is now ${ACCESS_META[access].label.toLowerCase()} for colleagues.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not change access");
    }
  }

  async function doUnshare() {
    if (!picker || !unshare) return;
    const r = unshare;
    setUnshare(null); setError(null);
    try {
      await filesFetch(`/api/v1/devices/${picker.deviceId}/folders/remove`, token!, {
        method: "POST", body: JSON.stringify({ path: r.path }),
      });
      setRoots((rs) => rs.filter((x) => x.path !== r.path));
      setTreeRoots((t) => ({
        ...t,
        [picker.deviceId]: (t[picker.deviceId] ?? []).filter((x) => x.path !== r.path),
      }));
      if (path.toLowerCase().startsWith(r.path.toLowerCase())) {
        setPath("");
        browse(picker.deviceId, "");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not stop sharing");
    }
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

  async function convert(e: RemoteFileEntry) {
    if (!picker) return;
    setError(null); setNotice(null);
    try {
      const r = await apiFetch<{ name: string }>(
        `/api/v1/devices/${picker.deviceId}/convert`, token!, {
          method: "POST", body: JSON.stringify({ path: e.path ?? e.rel_path }),
        });
      setNotice(`Converted — ${r.name} created next to the original.`);
      browse(picker.deviceId, path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "conversion failed");
    }
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
      a.href = url;
      a.download = e.is_dir ? `${e.name}.zip` : e.name;
      a.click();
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

  function entryMenu(e: RemoteFileEntry, p: string, dir: boolean, up = false) {
    return (
      <div className={`card absolute right-0 z-20 w-40 p-1.5 !bg-[var(--color-surface-3)] !shadow-[0_16px_40px_-8px_rgba(0,0,0,0.75)] ${
        up ? "bottom-full mb-1" : "top-full mt-1"}`}>
        <button className="menu-item" onClick={() => { download(e); setMenu(null); }}>
          <Download size={13} /> {dir ? "Download ZIP" : "Download"}
        </button>
        {!dir && /\.(docx?|odt|pptx?|xlsx?|txt|rtf)$/i.test(e.name) && (
          <button className="menu-item" onClick={() => { convert(e); setMenu(null); }}>
            <FileText size={13} /> Convert to PDF
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
    );
  }

  const currentRoot = roots.find((r) => path.toLowerCase().startsWith(r.path.toLowerCase()));
  const canWrite = !picker?.shared
    ? currentRoot?.access === "readwrite"
    : (picker.shared.permissions ?? 0) & 4;

  // ── device tree (left pane) ──

  async function toggleDevice(p: Picker) {
    setExpanded((e) => ({ ...e, [p.id]: !e[p.id] }));
    if (expanded[p.id] || p.shared || treeRoots[p.deviceId] !== undefined) return;
    const r = await filesFetch<{ roots?: Root[] }>(
      `/api/v1/devices/${p.deviceId}/browse?path=`, token!,
    ).catch(() => null);
    setTreeRoots((t) => ({
      ...t,
      [p.deviceId]: (r?.roots ?? []).map((x) => ({ ...x, label: x.label || basename(x.path) })),
    }));
  }

  function chooseFolder(p: Picker, r: Root) {
    if (p.id !== selected) setSelected(p.id);
    setEntries([]); setRoots([]); setSearchMode(false);
    browse(p.deviceId, r.path);
  }

  // group colleague shares by their owning device for the tree
  const sharedGroups = useMemo(() => {
    const g = new Map<string, { name: string; items: Picker[] }>();
    for (const p of pickers.filter((x) => x.shared)) {
      const cur = g.get(p.deviceId) ?? {
        name: p.shared!.device_name, items: [],
      };
      cur.items.push(p);
      g.set(p.deviceId, cur);
    }
    return [...g.values()];
  }, [pickers]);

  return (
    <div>
      <PageHeader title="Files"
        subtitle={picker ? `${picker.label}${picker.shared ? " · shared with you" : ""}` : "Browse, download and organize files on connected computers."}
        actions={
          <>
            <Dropdown className="min-w-[220px]" align="right" value={selected} onChange={select}
              placeholder="Choose a computer…"
              options={pickers.map((p) => ({
                value: p.id,
                label: p.shared ? (p.shared.label || basename(p.shared.root_path)) : p.label,
                hint: p.shared ? p.shared.device_name : p.status === "online" ? "online" : "offline",
                group: p.shared ? "Shared with me" : "My computers",
                icon: p.shared
                  ? <FolderArt size={16} tone="purple" />
                  : <span className="flex w-4 justify-center"><StatusDot status={p.status} /></span>,
              }))} />
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

      {/* toolbar: path bar + search + view toggle */}
      <div className="card mb-4 flex flex-wrap items-center gap-2 p-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5 pl-1">
          {searchMode ? (
            <button className="icon-btn" title="Back to folder"
              onClick={() => { setSearchMode(false); setSearchQ(""); browse(picker!.deviceId, path); }}>
              <ArrowLeft size={14} />
            </button>
          ) : (
            <button className="icon-btn" title="Up one level"
              disabled={!path || !parentPath(path)}
              onClick={() => picker && path && parentPath(path) && browse(picker.deviceId, parentPath(path)!)}>
              <ArrowLeft size={14} />
            </button>
          )}
          <nav className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto whitespace-nowrap text-[13px]">
            <HardDrive size={14} className="mx-1.5 shrink-0 text-[var(--color-text-faint)]" />
            {searchMode ? (
              <span className="text-[var(--color-text-dim)]">
                Results for <span className="font-medium text-[var(--color-text)]">“{searchQ}”</span>
                <span className="pill ml-2">{entries.length}</span>
              </span>
            ) : !path ? (
              <span className="text-[var(--color-text-dim)]">All shared folders</span>
            ) : (
              breadcrumbs().map((b, i, arr) => (
                <span key={b.path} className="flex items-center gap-0.5">
                  {i > 0 && <ChevronRight size={13} className="shrink-0 text-[var(--color-text-faint)]" />}
                  <button
                    className={`rounded-md px-1.5 py-1 transition-colors ${
                      i === arr.length - 1
                        ? "font-medium text-[var(--color-text)]"
                        : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
                    }`}
                    onClick={() => picker && browse(picker.deviceId, b.path)}>
                    {b.label}
                  </button>
                </span>
              ))
            )}
          </nav>
        </div>

        <form className="input flex w-full items-center gap-2 !py-[7px] sm:w-72"
          onSubmit={(e) => { e.preventDefault(); if (searchQ.trim() && picker) { setSearchMode(true); search(picker.deviceId, searchQ); } }}>
          <Search size={14} className="shrink-0 text-[var(--color-text-faint)]" />
          <input className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
            placeholder={`Search ${picker?.label ?? "files"}…`}
            value={searchQ} onChange={(e) => setSearchQ(e.target.value)} />
          {searchQ ? (
            <button type="button" className="shrink-0 rounded p-0.5 text-[var(--color-text-faint)] hover:text-[var(--color-text)]"
              title="Clear" onClick={() => {
                setSearchQ("");
                if (searchMode && picker) { setSearchMode(false); browse(picker.deviceId, path); }
              }}>
              <X size={13} />
            </button>
          ) : <kbd>Enter</kbd>}
        </form>

        <div className="segmented !p-0.5">
          <button className={`tab !px-2 !py-1.5 ${viewMode === "grid" ? "tab-active" : ""}`}
            title="Grid view" onClick={() => setViewMode("grid")}>
            <LayoutGrid size={14} />
          </button>
          <button className={`tab !px-2 !py-1.5 ${viewMode === "list" ? "tab-active" : ""}`}
            title="List view" onClick={() => setViewMode("list")}>
            <List size={14} />
          </button>
        </div>
      </div>

      {error && (
        <div className="card mb-4 flex items-center gap-2 px-4 py-3 text-sm text-[var(--color-danger)]">
          <CloudOff size={15} /> {error}
        </div>
      )}
      {notice && (
        <div className="card mb-4 flex items-center gap-2 px-4 py-3 text-sm text-[var(--color-online)]">
          <Check size={15} /> {notice}
        </div>
      )}

      {/* two-pane: device tree + entries */}
      <div className="grid gap-4 lg:grid-cols-[230px_1fr]">
        <div className="card hidden max-h-[calc(100vh-15.5rem)] self-start overflow-y-auto p-2 lg:block">
          {pickers.filter((p) => !p.shared).map((p) => (
            <div key={p.id}>
              <button
                className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-[var(--color-surface-2)]"
                onClick={() => toggleDevice(p)}>
                <ChevronRight size={12}
                  className={`shrink-0 text-[var(--color-text-dim)] transition-transform ${expanded[p.id] ? "rotate-90" : ""}`} />
                <Monitor size={14} className="shrink-0 text-[var(--color-text-dim)]" />
                <span className="min-w-0 flex-1 truncate font-medium">{p.label}</span>
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${p.status === "online" ? "bg-[var(--color-online)]" : "bg-[var(--color-surface-3)]"}`} />
              </button>
              {expanded[p.id] && (
                <div className="mb-1 ml-5 space-y-0.5 border-l border-[var(--color-border)] pl-2">
                  {(treeRoots[p.deviceId] ?? []).map((r) => (
                    <button key={r.path}
                      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                        selected === p.id && path.toLowerCase().startsWith(r.path.toLowerCase())
                          ? "bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)]"
                          : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
                      }`}
                      onClick={() => chooseFolder(p, r)}>
                      <Folder size={13} className="shrink-0" />
                      <span className="truncate">{r.label}</span>
                    </button>
                  ))}
                  {treeRoots[p.deviceId] === undefined && (
                    <div className="px-2 py-1.5 text-xs text-[var(--color-text-dim)]"><Spinner size={11} /></div>
                  )}
                  {(treeRoots[p.deviceId] ?? []).length === 0 && treeRoots[p.deviceId] !== undefined && (
                    <div className="px-2 py-1.5 text-[11px] text-[var(--color-text-dim)]">
                      {p.status === "online" ? "No shared folders" : "Offline"}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {sharedGroups.length > 0 && (
            <div className="mt-3 border-t border-[var(--color-border)] pt-2">
              <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
                Colleagues
              </div>
              {sharedGroups.map((g) => (
                <div key={g.name}>
                  <div className="flex items-center gap-1.5 px-2 py-1.5 text-sm">
                    <Monitor size={14} className="shrink-0 text-[var(--color-text-dim)]" />
                    <span className="truncate font-medium">{g.name}</span>
                  </div>
                  <div className="mb-1 ml-5 space-y-0.5 border-l border-[var(--color-border)] pl-2">
                    {g.items.map((p) => (
                      <button key={p.id}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                          selected === p.id
                            ? "bg-[rgba(139,92,246,0.15)] text-[var(--color-accent)]"
                            : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]"
                        }`}
                        onClick={() => select(p.id)}>
                        <Folder size={13} className="shrink-0" />
                        <span className="truncate">{p.shared!.label || basename(p.shared!.root_path)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          {pickers.length === 0 && (
            <div className="px-2.5 py-3 text-xs text-[var(--color-text-dim)]">
              No computers — pair one first.
            </div>
          )}
        </div>

        <div className="card max-h-[calc(100vh-15.5rem)] min-h-[260px] overflow-y-auto">
        {loading ? (
          <div className="p-10 text-center"><Spinner /></div>
        ) : entries.length === 0 ? (
          <div className="p-10 text-center text-sm text-[var(--color-text-dim)]">
            {searchMode ? "No matches." : path ? "Empty folder." :
              picker?.shared ? "" : "No shared folders yet — add one under Devices → Folders."}
          </div>
        ) : viewMode === "grid" ? (
          <div className="grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 xl:grid-cols-4">
            {entries.map((e, i) => {
              const p = e.path ?? e.rel_path;
              const dir = !!e.is_dir;
              return (
                <div key={p}
                  className="group relative overflow-visible rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition-all hover:border-[var(--color-border-strong)] hover:shadow-[0_8px_24px_-12px_rgba(0,0,0,0.7)]">
                  <div className="absolute right-1.5 top-1.5 z-10">
                    <button className="icon-btn !h-7 !w-7 opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={() => setMenu(menu === p ? null : p)}>···</button>
                    {menu === p && entryMenu(e, p, dir, i >= 4 && i >= entries.length - 4)}
                  </div>
                  <button className="flex w-full flex-col items-center px-3 pb-3.5 pt-5"
                    onClick={() => dir ? open(e) : download(e)}>
                    <div className="flex h-[60px] items-center transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:scale-[1.04]">
                      {dir ? <FolderArt size={64} /> : <FileIcon name={e.name} size={48} />}
                    </div>
                    <span className="mt-3 w-full truncate text-center text-[13px] font-medium">{e.name}</span>
                    <span className="pill mt-1.5">
                      {dir ? "Folder" : formatBytes(e.size ?? 0)}
                    </span>
                  </button>
                  {(tags[p] ?? []).length > 0 && (
                    <div className="flex flex-wrap justify-center gap-1 border-t border-[var(--color-border)] px-2 py-2">
                      {(tags[p] ?? []).slice(0, 3).map((t) => <span key={t} className="chip">{t}</span>)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="bg-[var(--color-surface-2)] text-left text-xs text-[var(--color-text-dim)] shadow-[0_1px_0_var(--color-border)]">
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Tags</th>
                <th className="px-4 py-2.5 font-medium">Size</th>
                <th className="hidden px-4 py-2.5 font-medium md:table-cell">Modified</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => {
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
                        {menu === p && entryMenu(e, p, dir, i >= 3 && i >= entries.length - 3)}
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
      {roots.length > 0 && (
        <div className="mt-5">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-sm font-semibold">{picker?.shared ? "Shared with you" : "Shared folders"}</h2>
            <span className="pill">{roots.length}</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {roots.map((r) => {
              const own = !picker?.shared && r.access !== "granted";
              const meta = ACCESS_META[r.access];
              return (
                <div key={r.path}
                  className="card group relative flex flex-col items-center px-4 pb-0 pt-6 text-center">
                  {own && (
                    <button
                      className="icon-btn absolute right-2.5 top-2.5 !h-7 !w-7 text-[var(--color-text-faint)] opacity-0 transition-opacity hover:!text-[var(--color-danger)] group-hover:opacity-100"
                      title="Stop sharing this folder"
                      onClick={() => setUnshare(r)}>
                      <FolderX size={14} />
                    </button>
                  )}
                  <button className="flex w-full min-w-0 flex-col items-center"
                    onClick={() => picker && browse(picker.deviceId, r.path)}>
                    <div className="flex h-[72px] items-center transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:scale-[1.04]">
                      {FILE_ROOT_RE.test(r.label)
                        ? <FileIcon name={r.label} size={56} />
                        : <FolderArt size={76} />}
                    </div>
                    <span className="mt-3 max-w-full truncate text-[15px] font-semibold">{r.label}</span>
                    <span className="pill mt-2">
                      {picker?.shared ? picker.shared.device_name : picker?.label}
                    </span>
                    <span className="mt-1.5 max-w-full truncate text-[11px] text-[var(--color-text-faint)]"
                      title={r.path}>
                      {r.path}
                    </span>
                  </button>
                  <div className="mt-4 w-full space-y-2 border-t border-[var(--color-border)] py-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-[var(--color-text-dim)]">Owner</span>
                      <span className="font-medium">
                        {own ? "You" : picker?.shared?.owner_email ?? picker?.shared?.device_name ?? "Colleague"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[var(--color-text-dim)]">Access</span>
                      {own ? (
                        <div className="relative">
                          <button
                            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                              r.access === "readwrite"
                                ? "border-[rgba(139,92,246,0.45)] bg-[rgba(139,92,246,0.12)] text-[var(--color-accent)]"
                                : "border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-dim)] hover:text-[var(--color-text)]"
                            }`}
                            onClick={() => setAccessMenu(accessMenu === r.path ? null : r.path)}>
                            {r.access === "readwrite" ? <Pencil size={10} /> : <Eye size={10} />}
                            {meta?.label ?? r.access}
                            <ChevronDown size={11} />
                          </button>
                          {accessMenu === r.path && (
                            <>
                              <div className="fixed inset-0 z-20" onClick={() => setAccessMenu(null)} />
                              <div className="card pop-in absolute right-0 bottom-full z-30 mb-1.5 w-60 p-1.5 text-left">
                                {(["read", "readwrite"] as const).map((a) => (
                                  <button key={a} className="menu-item" onClick={() => setAccess(r, a)}>
                                    {a === "read"
                                      ? <Eye size={13} className="shrink-0 text-[var(--color-text-dim)]" />
                                      : <Pencil size={13} className="shrink-0 text-[var(--color-accent)]" />}
                                    <span className="min-w-0 flex-1">
                                      <span className="block">{ACCESS_META[a].label}</span>
                                      <span className="block text-[10px] text-[var(--color-text-faint)]">
                                        {ACCESS_META[a].desc}
                                      </span>
                                    </span>
                                    <Check size={13}
                                      className={`shrink-0 text-[var(--color-accent)] ${r.access === a ? "" : "invisible"}`} />
                                  </button>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                      ) : (
                        <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-dim)]">
                          {meta?.label ?? r.access}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
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
      {unshare && (
        <ConfirmDialog
          title={`Stop sharing ${unshare.label}?`}
          body="The folder stays on this computer, but colleagues immediately lose access to it."
          confirmLabel="Stop sharing" danger
          onConfirm={doUnshare} onCancel={() => setUnshare(null)}
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
