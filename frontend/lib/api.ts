/** Thin client for the FastAPI coordinator. Attaches the Supabase JWT. */

const API_URL = process.env.NEXT_PUBLIC_CLOUD_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  accessToken: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail?.error ?? `request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export { API_URL };
