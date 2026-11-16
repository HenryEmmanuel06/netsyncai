"use client";

import { useEffect, useState } from "react";
import { SendHorizontal, ShieldAlert } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import type { TaskResult } from "@/types";

interface Message {
  prompt: string;
  result?: TaskResult;
  error?: string;
  pending?: boolean;
}

export default function AssistantPage() {
  const [token, setToken] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<Message[]>([]);

  useEffect(() => {
    (async () => {
      if (!supabaseConfigured) return;
      const sb = getSupabaseBrowser();
      const { data } = await sb!.auth.getSession();
      setToken(data.session?.access_token ?? null);
    })();
  }, []);

  async function run(p: string, confirm: boolean) {
    return apiFetch<TaskResult>("/api/v1/ai/task", token!, {
      method: "POST",
      body: JSON.stringify({ prompt: p, confirm }),
    });
  }

  async function submit(e: React.FormEvent, confirm = false) {
    e.preventDefault();
    const p = prompt.trim();
    if (!p || !token) return;
    setPrompt("");
    setHistory((h) => [{ prompt: p, pending: true }, ...h]);
    try {
      const result = await run(p, confirm);
      setHistory((h) =>
        h.map((m) => (m.prompt === p && m.pending ? { prompt: p, result } : m))
      );
    } catch (err) {
      setHistory((h) =>
        h.map((m) =>
          m.prompt === p && m.pending
            ? { prompt: p, error: err instanceof Error ? err.message : "failed" }
            : m
        )
      );
    }
  }

  async function confirmStep(msg: Message) {
    setHistory((h) => h.map((m) => (m === msg ? { ...msg, pending: true } : m)));
    try {
      const result = await run(msg.prompt, true);
      setHistory((h) => h.map((m) => (m === msg ? { ...msg, result, pending: false } : m)));
    } catch {
      setHistory((h) => h.map((m) => (m === msg ? { ...msg, pending: false } : m)));
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <h1 className="text-2xl font-semibold">AI Assistant</h1>
      <p className="mt-1 text-sm text-[var(--color-text-dim)]">
        Describe a file task — the planner turns it into validated operations on
        your devices. Destructive plans ask for confirmation first.
      </p>

      <div className="mt-6 flex-1 space-y-3 overflow-y-auto">
        {history.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            Try: <em>"search my files for proposal"</em>, <em>"create a folder
            called Backups"</em>, <em>"show my device status"</em>.
            Needs <code>GEMINI_API_KEY</code> on the backend.
          </div>
        )}
        {history.map((m, i) => (
          <div key={i} className="space-y-2">
            <div className="card border-l-2 border-l-[var(--color-primary)] p-3 text-sm">{m.prompt}</div>
            {m.pending && <div className="text-xs text-[var(--color-text-dim)]">planning…</div>}
            {m.error && <div className="card p-3 text-sm text-red-400">{m.error}</div>}
            {m.result && (
              <div className="card space-y-2 p-3 text-sm">
                {m.result.summary && <div className="text-[var(--color-text-dim)]">{m.result.summary}</div>}
                {m.result.needs_confirmation && !m.result.executed && (
                  <button
                    onClick={() => confirmStep(m)}
                    className="flex items-center gap-2 rounded bg-red-950/50 px-3 py-1.5 text-xs text-red-300"
                  >
                    <ShieldAlert size={14} /> Plan contains destructive ops — confirm to run
                  </button>
                )}
                {m.result.steps.map((s, j) => (
                  <div key={j} className="flex items-start gap-2 text-xs">
                    <span className={s.ok === true ? "text-green-400" : s.ok === false ? "text-red-400" : "text-[var(--color-text-dim)]"}>
                      {s.ok === true ? "✓" : s.ok === false ? "✗" : "•"}
                    </span>
                    <div>
                      <span className="font-mono">{s.tool}</span>
                      {s.device && <span className="text-[var(--color-text-dim)]"> on {s.device}</span>}
                      {s.error && <div className="text-red-400">{s.error}</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="mt-4 flex gap-2 pb-2">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask NetSync to find, download, or sync files…"
          className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3 outline-none focus:border-[var(--color-primary)]"
        />
        <button type="submit" className="rounded-lg bg-[var(--color-primary)] px-4 text-white" aria-label="Send">
          <SendHorizontal size={18} />
        </button>
      </form>
    </div>
  );
}
