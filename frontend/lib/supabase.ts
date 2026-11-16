import { createBrowserClient } from "@supabase/ssr";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabaseConfigured = Boolean(url && anonKey);

/** Browser client — anon key only. Returns null if env not configured so
 *  pages can render a "configure Supabase" state instead of crashing. */
export function getSupabaseBrowser(): SupabaseClient | null {
  if (!url || !anonKey) return null;
  return createBrowserClient(url, anonKey);
}

export { createClient };
