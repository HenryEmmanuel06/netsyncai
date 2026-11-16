/** Thin client for the FastAPI coordinator. Attaches the Supabase JWT. */

const API_URL = process.env.NEXT_PUBLIC_CLOUD_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  accessToken: string,
  init: RequestInit = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new Error(
      `Can't reach the NetSync backend (${API_URL}). It may still be starting — wait a minute and retry.`,
    );
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail?.error ?? `request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export { API_URL };
