# Deployment Guide

NetSync AI has three deployable parts: **frontend** (Vercel), **cloud backend**
(Render or any Docker host), and **desktop agent** (GitHub Releases download).

## 1. Supabase (database + auth)

1. Project: https://supabase.com → your project → **SQL Editor**
2. Run `supabase/migrations/0001_initial_schema.sql`
3. Run `supabase/migrations/0002_device_credentials.sql`
4. **Settings → API**: copy `URL`, `anon key`, `service_role key`, and
   **JWT Secret** (Settings → API → JWT Settings)

## 2. Cloud backend → Render

1. https://render.com → **New → Web Service** → connect the GitHub repo
2. Settings:
   - **Root Directory**: `cloud_backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Instance type: free is fine (cold-starts ~30s)
3. Environment variables:

   | Key | Value |
   |---|---|
   | `SUPABASE_URL` | `https://<project>.supabase.co` |
   | `SUPABASE_SERVICE_ROLE_KEY` | service_role key (secret) |
   | `SUPABASE_JWT_SECRET` | JWT secret |
   | `DEVICE_STORE` | `supabase` |
   | `CORS_ORIGINS` | `["https://<your-app>.vercel.app"]` |
   | `GEMINI_API_KEY` | your Gemini key (AI features) |
   | `GEMINI_MODEL` | `gemini-2.0-flash-lite` |

   (`render.yaml` in the repo root encodes this — use **New → Blueprint**
   instead if you prefer.)

4. Verify: `https://<service>.onrender.com/health` → `{"status":"ok"}`

## 3. Frontend → Vercel

1. https://vercel.com → **Import project** → repo → **Root Directory: `frontend`**
2. Environment variables:

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<project>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon key |
   | `NEXT_PUBLIC_CLOUD_API_URL` | `https://<service>.onrender.com` |

3. Deploy → note the URL → add it to the backend's `CORS_ORIGINS` and redeploy.

## 4. Desktop agent → GitHub Releases

The agent is already built at `desktop_agent/dist/netsync-agent.exe`.

```powershell
# rebuild after agent code changes:
cd desktop_agent
.\.venv\Scripts\pyinstaller.exe --noconfirm agent.spec

# publish a release (GitHub CLI):
gh release create v0.1.0 dist\netsync-agent.exe `
  --title "NetSync Agent v0.1.0" `
  --notes "Windows agent — run: netsync-agent pair <CODE> then netsync-agent run"
```

Or via web UI: repo → **Releases → Draft a new release** → tag `v0.1.0` →
attach `netsync-agent.exe` → Publish. Users download it from
`https://github.com/<you>/netsyncai/releases`.

**Optional — full installer**: install Inno Setup, then compile
`installer\netsync.iss` (right-click → Compile) → attach the produced
`NetSyncAI-Setup.exe` to the same release.

### On a user's PC
```powershell
netsync-agent pair <8-char code from the web UI>
netsync-agent index C:\Users\Me\Documents --access readwrite
netsync-agent run
```
Data lives in `%LOCALAPPDATA%\NetSyncAI`. To run at boot: Task Scheduler →
New Task → trigger "At log on" → action `netsync-agent.exe run` (the tray
app is a later refinement).

## Env quick reference

| Service | Must NOT contain |
|---|---|
| frontend (NEXT_PUBLIC_*) | service_role key, JWT secret, Gemini key |
| agent | any API keys — pairing codes only |
