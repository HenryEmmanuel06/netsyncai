"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Check, SendHorizontal, ShieldAlert, X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/useAuth";
import { Spinner } from "@/components/ui";
import type { TaskResult } from "@/types";

interface Message {
  prompt: string;
  result?: TaskResult;
  error?: string;
  pending?: boolean;
}

const EXAMPLES = [
  "Search my computers for files named proposal",
  "Show the status of my devices",
  "Search for PDF files on my laptop",
  "Create a folder called Backups",
];

export default function AssistantPage() {
  const { token } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<Message[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

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
    const stamp = Date.now();
    setHistory((h) => [...h, { prompt: p, pending: true }]);
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
    void stamp;
  }

  async function confirmStep(msg: Message) {
    setHistory((h) => h.map((m) => (m === msg ? { ...msg, pending: true } : m)));
    try {
      const result = await run(msg.prompt, true);
      setHistory((h) => h.map((m) => (m === msg ? { ...msg, result, pending: false } : m)));
    } catch (err) {
      setHistory((h) => h.map((m) => (m === msg ? { ...msg, pending: false,
        error: err instanceof Error ? err.message : "failed" } : m)));
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="mb-4 flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#8b5cf6] to-[#5f32d6]">
          <Bot size={19} className="text-white" />
        </span>
        <div>
          <h1 className="text-xl font-semibold">AI Assistant</h1>
          <p className="text-xs text-[var(--color-text-dim)]">
            Describe a task — it plans validated steps across your computers.
            Destructive plans ask first.
          </p>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {history.length === 0 && (
          <div className="card mx-auto mt-10 max-w-md p-5">
            <div className="mb-3 text-sm font-medium">Try asking…</div>
            <div className="space-y-2">
              {EXAMPLES.map((ex) => (
                <button key={ex} onClick={() => setPrompt(ex)}
                  className="block w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-left text-sm text-[var(--color-text-dim)] hover:border-[var(--color-primary)] hover:text-[var(--color-text)]">
                  “{ex}”
                </button>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-[var(--color-text-dim)]">
              Requires GEMINI_API_KEY configured on the backend.
            </p>
          </div>
        )}

        {history.map((m, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-[var(--color-primary)] px-4 py-2.5 text-sm text-white">
                {m.prompt}
              </div>
            </div>
            {m.pending && (
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-dim)]">
                <Spinner size={12} /> planning…
              </div>
            )}
            {m.error && (
              <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-[rgba(248,113,113,0.1)] px-4 py-2.5 text-sm text-[var(--color-danger)]">
                {m.error}
              </div>
            )}
            {m.result && (
              <div className="max-w-[85%] space-y-2 rounded-2xl rounded-bl-sm bg-[var(--color-surface-2)] px-4 py-3 text-sm">
                {m.result.summary && <div>{m.result.summary}</div>}
                {m.result.needs_confirmation && !m.result.executed && (
                  <button
                    onClick={() => confirmStep(m)}
                    className="flex items-center gap-2 rounded-lg bg-[rgba(248,113,113,0.15)] px-3 py-2 text-xs font-medium text-[var(--color-danger)]">
                    <ShieldAlert size={14} /> This plan can change or delete files — run it anyway?
                  </button>
                )}
                {m.result.steps.map((s, j) => (
                  <div key={j} className="flex items-start gap-2 text-xs">
                    <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${
                      s.ok === true ? "bg-[rgba(52,211,153,0.2)] text-[var(--color-online)]"
                        : s.ok === false ? "bg-[rgba(248,113,113,0.2)] text-[var(--color-danger)]"
                        : "bg-[var(--color-surface-3)] text-[var(--color-text-dim)]"}`}>
                      {s.ok === true ? <Check size={9} /> : s.ok === false ? <X size={9} /> : "•"}
                    </span>
                    <div>
                      <span className="font-mono">{s.tool}</span>
                      {s.device && <span className="text-[var(--color-text-dim)]"> on {s.device}</span>}
                      {s.error && <div className="text-[var(--color-danger)]">{s.error}</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={submit} className="mt-4 flex items-center gap-2 pb-2">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask NetSync to find, download, or sync files…"
          className="input flex-1 !py-3"
        />
        <button type="submit" className="btn btn-primary !p-3" aria-label="Send">
          <SendHorizontal size={17} />
        </button>
      </form>
    </div>
  );
}
