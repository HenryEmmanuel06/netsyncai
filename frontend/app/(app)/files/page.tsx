"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import type { Device, RemoteFileEntry, SharedFolder } from "@/types";
import {
  Download, FilePlus2, FolderPlus, Pencil, RefreshCw, Search, Trash2,
} from "lucide-react";

interface RootFolder {
  id: number;
  path: string;
  label: string;
  access: string;
}

interface BrowseResult {
  path: string;
  entries: RemoteFileEntry[];
  roots: RootFolder[] | null;
}

const API = process.env.NEXT_PUBLIC_CLOUD_API_URL ?? "http://localhost:8000";

export default function FilesPage() {
  const [token, setToken] = useState<string | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [shared, setShared] = useState<SharedFolder[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [roots, setRoots] = useState<RootFolder[]>([]);
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<RemoteFileEntry[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RemoteFileEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      if (!supabaseConfigured) { setError("Supabase not configured"); return; }
      const sb = getSupabaseBrowser();
      const { data } = await sb!.auth.getSession();
      if (!data.session) { setError("Sign in first"); return; }
      setToken(data.session.access_token);
      const [devs, shares] = await Promise.all([
        apiFetch<Device[]>("/api/v1/devices", data.session.access_token),
        apiFetch<{ owned: SharedFolder[]; granted: SharedFolder[] }>(
          "/api/v1/sharing", data.session.access_token,
        ),
      ]);
      setDevices(devs.filter((d) => !d.revoked_at));
      setShared(shares.granted);
    })();
  }, []);

  const browse = useCallback(async (devId: string, p: string) => {
    if (!token) return;
    setError(null);
    try {
      const r = await apiFetch<BrowseResult>(
        `/api/v1/devices/${devId}/browse?path=${encodeURIComponent(p)}`, token,
      );
      if (r.roots) setRoots(r.roots);
      setEntries(r.entries);
      setPath(p);
      setResults(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "browse failed");
    }
  }, [token]);

  function selectDevice(sel: string) {
    setPath("");
    setRoots([]);
    setEntries([]);
    setResults(null);
    if (sel.startsWith("shared:")) {
      const share = shared.find((s) => `shared:${s.id}` === sel);
      if (!share) return;
      setDeviceId(share.device_id);
      browse(share.device_id, share.root_path);
      return;
    }
    setDeviceId(sel);
    if (sel) browse(sel, "");
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !deviceId) return;
    const r = await apiFetch<{ results: RemoteFileEntry[] }>(
      `/api/v1/devices/${deviceId}/search?q=${encodeURIComponent(query)}`, token,
    );
    setResults(r.results);
  }

  async function op(fn: () => Promise<unknown>, ok: string) {
    setError(null);
    try {
      await fn();
      setNotice(ok);
      setTimeout(() => setNotice(null), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "operation failed");
    }
  }

  async function rename(e: RemoteFileEntry) {
    const name = window.prompt("New name:", e.name);
    if (!name || name === e.name) return;
    await op(async () => {
      await apiFetch(`/api/v1/devices/${deviceId}/rename`, token!, {
        method: "POST",
        body: JSON.stringify({ path: e.rel_path, new_name: name }),
      });
      await browse(deviceId, path);
    }, `renamed to ${name}`);
  }

  async function mkdir() {
    const name = window.prompt("Folder name:");
    if (!name) return;
    const sep = path.includes("\\") ? "\\" : "/";
    await op(async () => {
      await apiFetch(`/api/v1/devices/${deviceId}/mkdir`, token!, {
        method: "POST",
        body: JSON.stringify({ path: `${path}${path ? sep : ""}${name}` }),
      });
      await browse(deviceId, path);
    }, `created ${name}`);
  }

  async function del(e: RemoteFileEntry) {
    if (!window.confirm(`Delete ${e.name}? This cannot be undone.`)) return;
    await op(async () => {
      await apiFetch(
        `/api/v1/devices/${deviceId}/file?path=${encodeURIComponent(e.rel_path)}`,
        token!, { method: "DELETE" },
      );
      await browse(deviceId, path);
    }, `deleted ${e.name}`);
  }

  function download(e: RemoteFileEntry) {
    // stream through the coordinator relay; attach the JWT via header
    fetch(`${API}/api/v1/devices/${deviceId}/download?path=${encodeURIComponent(e.rel_path)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`download failed: ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = e.name;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch((err) => setError(err.message));
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold">Network Files</h1>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          value={deviceId}
          onChange={(e) => selectDevice(e.target.value)}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm"
        >
          <option value="">Select a device…</option>
          {devices.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({d.status})
            </option>
          ))}
          {shared.length > 0 && (
            <optgroup label="Shared with you">
              {shared.map((s) => (
                <option key={s.id} value={`shared:${s.id}`}>
                  {s.label || s.root_path} — {s.device_name}
                </option>
              ))}
            </optgroup>
          )}
        </select>

        <form onSubmit={search} className="flex flex-1 gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search indexed files…"
            className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm"
          />
          <button className="rounded-lg bg-[var(--color-surface-2)] px-3" aria-label="Search">
            <Search size={16} />
          </button>
        </form>

        {deviceId && (
          <>
            <button onClick={() => browse(deviceId, path)} className="rounded-lg bg-[var(--color-surface-2)] p-2" aria-label="Refresh">
              <RefreshCw size={16} />
            </button>
            <button onClick={mkdir} className="rounded-lg bg-[var(--color-surface-2)] p-2" aria-label="New folder">
              <FolderPlus size={16} />
            </button>
          </>
        )}
      </div>

      {roots.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {roots.map((r) => (
            <button
              key={r.id}
              onClick={() => browse(deviceId, r.path)}
              className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-sm hover:border-[var(--color-primary)]"
            >
              {r.label || r.path} <span className="text-xs text-[var(--color-text-dim)]">({r.access})</span>
            </button>
          ))}
        </div>
      )}

      {error && <div className="card mt-4 p-3 text-sm text-red-400">{error}</div>}
      {notice && <div className="card mt-4 p-3 text-sm text-green-400">{notice}</div>}

      {path && (
        <div className="mt-4 text-sm text-[var(--color-text-dim)]">
          {path}
        </div>
      )}

      <div className="mt-4 space-y-1">
        {(results ?? entries).map((e) => (
          <div key={e.rel_path} className="card flex items-center justify-between px-4 py-2.5 text-sm">
            <button
              className="flex-1 text-left"
              onClick={() => e.is_dir && browse(deviceId, e.rel_path)}
            >
              <span className={e.is_dir ? "font-medium text-[var(--color-primary)]" : ""}>
                {e.is_dir ? "📁 " : ""}{e.name}
              </span>
              {e.size != null && (
                <span className="ml-3 text-xs text-[var(--color-text-dim)]">
                  {(e.size / 1024).toFixed(1)} KB
                </span>
              )}
            </button>
            {!e.is_dir && (
              <div className="flex gap-1">
                <button onClick={() => download(e)} className="p-1.5 text-[var(--color-text-dim)] hover:text-[var(--color-text)]" aria-label="Download">
                  <Download size={15} />
                </button>
                <button onClick={() => rename(e)} className="p-1.5 text-[var(--color-text-dim)] hover:text-[var(--color-text)]" aria-label="Rename">
                  <Pencil size={15} />
                </button>
                <button onClick={() => del(e)} className="p-1.5 text-[var(--color-text-dim)] hover:text-red-400" aria-label="Delete">
                  <Trash2 size={15} />
                </button>
              </div>
            )}
          </div>
        ))}
        {deviceId && (results ?? entries).length === 0 && !error && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            {results ? "No matches." : "Nothing here. Index a folder on the agent first: python main.py index <folder> --access readwrite"}
          </div>
        )}
      </div>
    </div>
  );
}
