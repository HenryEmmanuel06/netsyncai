/** Thin client for the FastAPI coordinator. Attaches the Supabase JWT. */

const API_URL = process.env.NEXT_PUBLIC_CLOUD_API_URL ?? "http://localhost:8000";
const API_URL_BACKUP = process.env.NEXT_PUBLIC_CLOUD_API_URL_BACKUP ?? "";

/** When the primary backend is unreachable we pin this session to the
 *  failover backend for a while instead of paying a timeout per request. */
let failoverUntil = 0;

function activeUrl(): string {
  if (API_URL_BACKUP && Date.now() < failoverUntil) return API_URL_BACKUP;
  return API_URL;
}

async function rawFetch(base: string, path: string, accessToken: string,
  init: RequestInit): Promise<Response> {
  return fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(init.headers ?? {}),
    },
  });
}

export async function apiFetch<T>(
  path: string,
  accessToken: string,
  init: RequestInit = {},
): Promise<T> {
  const base = activeUrl();
  let res: Response;
  try {
    res = await rawFetch(base, path, accessToken, init);
  } catch {
    // network-level failure on the primary → switch to the failover backend
    if (API_URL_BACKUP && base === API_URL) {
      try {
        res = await rawFetch(API_URL_BACKUP, path, accessToken, init);
        failoverUntil = Date.now() + 60_000;
      } catch {
        throw new Error(
          `Can't reach the NetSync backend. Both ${API_URL} and the backup are down — wait a minute and retry.`,
        );
      }
    } else {
      throw new Error(
        `Can't reach the NetSync backend (${base}). It may still be starting — wait a minute and retry.`,
      );
    }
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail?.error ?? `request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export { API_URL, API_URL_BACKUP, activeUrl };
