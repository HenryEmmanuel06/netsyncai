"use client";

import { useState } from "react";
import { SendHorizontal } from "lucide-react";

/**
 * AI Assistant — primary landing page.
 * Phase 5 wires this to POST /api/v1/tasks (LLM → validated plan → dispatch).
 * For now the prompt box validates input and shows the planned flow.
 */
export default function AssistantPage() {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<string[]>([]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setHistory((h) => [prompt, ...h]);
    setPrompt("");
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <h1 className="text-2xl font-semibold">AI Assistant</h1>
      <p className="mt-1 text-sm text-[var(--color-text-dim)]">
        Describe a file task. Use <code>@</code> to mention users and devices —
        e.g. <code>@Aje find proposal.docx and download it</code>.
      </p>

      <div className="mt-6 flex-1 space-y-2 overflow-y-auto">
        {history.length === 0 && (
          <div className="card p-4 text-sm text-[var(--color-text-dim)]">
            Task execution connects in Phase 5 (AI integration). Phase 2–4
            deliver the device connectivity and file operations it will drive.
          </div>
        )}
        {history.map((p, i) => (
          <div key={i} className="card p-3 text-sm">{p}</div>
        ))}
      </div>

      <form onSubmit={submit} className="mt-4 flex gap-2 pb-2">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask NetSync to find, send, convert, or sync files…"
          className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3 outline-none focus:border-[var(--color-primary)]"
        />
        <button
          type="submit"
          className="rounded-lg bg-[var(--color-primary)] px-4 text-white"
          aria-label="Send"
        >
          <SendHorizontal size={18} />
        </button>
      </form>
    </div>
  );
}
