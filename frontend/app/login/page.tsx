"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Boxes } from "lucide-react";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";
import { Spinner } from "@/components/ui";

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
      router.push("/dashboard");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-7">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#8b5cf6] to-[#5f32d6]">
            <Boxes size={18} className="text-white" />
          </span>
          <span className="font-semibold">NetSync AI</span>
        </Link>
        <h1 className="pt-2 text-xl font-semibold">
          {mode === "signin" ? "Welcome back" : "Create your account"}
        </h1>
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="input w-full"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Password (min 8 chars)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="input w-full"
        />
        {message && (
          <p className="text-sm text-[var(--color-text-dim)]">{message}</p>
        )}
        <button type="submit" disabled={busy}
          className="btn btn-primary w-full justify-center !py-2.5">
          {busy ? <Spinner size={15} /> : mode === "signin" ? "Sign in" : "Sign up"}
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
