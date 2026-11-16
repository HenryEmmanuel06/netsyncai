"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getSupabaseBrowser, supabaseConfigured } from "@/lib/supabase";

export interface Auth {
  token: string | null;
  email: string | null;
  userId: string | null;
  ready: boolean;
  configured: boolean;
  signOut: () => Promise<void>;
}

export function useAuth(): Auth {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [ready, setReady] = useState(!supabaseConfigured);

  useEffect(() => {
    const sb = getSupabaseBrowser();
    if (!sb) return;
    let mounted = true;
    sb.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      const s = data.session;
      if (!s) {
        router.replace("/login");
        return;
      }
      setToken(s.access_token);
      setEmail(s.user.email ?? null);
      setUserId(s.user.id);
      setReady(true);
    });
    const { data: sub } = sb.auth.onAuthStateChange((_e, s) => {
      if (!s) router.replace("/login");
    });
    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, [router]);

  const signOut = useCallback(async () => {
    await getSupabaseBrowser()?.auth.signOut();
    router.replace("/login");
  }, [router]);

  return { token, email, userId, ready, configured: supabaseConfigured, signOut };
}
