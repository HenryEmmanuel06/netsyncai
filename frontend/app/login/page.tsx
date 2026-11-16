"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!supabaseConfigured) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="card max-w-md p-6 text-sm text-[var(--color-text-dim)]">
          Supabase is not configured. Set
          <code className="mx-1">NEXT_PUBLIC_SUPABASE_URL</code> and
          <code className="mx-1">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>
          in <code>.env.local</code>.
        </div>
      </main>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const supabase = getSupabaseBrowser();
    if (!supabase) return;
    setBusy(true);
    setMessage(null);
    const { error } =
      mode === "signin"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    setBusy(false);
    if (error) {
      setMessage(error.message);
    } else if (mode === "signup") {
      setMessage("Check your email to verify your account, then sign in.");
    } else {
      router.push("/assistant");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <h1 className="text-xl font-semibold">
          {mode === "signin" ? "Sign in" : "Create account"}
        </h1>
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 outline-none focus:border-[var(--color-primary)]"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Password (min 8 chars)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 outline-none focus:border-[var(--color-primary)]"
        />
        {message && (
          <p className="text-sm text-[var(--color-text-dim)]">{message}</p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-[var(--color-primary)] py-2 font-medium text-white disabled:opacity-50"
        >
          {busy ? "…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>
        <button
          type="button"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          className="w-full text-sm text-[var(--color-text-dim)] hover:text-[var(--color-text)]"
        >
          {mode === "signin"
            ? "Need an account? Sign up"
            : "Have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
