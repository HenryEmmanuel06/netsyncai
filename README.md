# NetSync AIs

AI-driven multi-agent distributed file management and synchronization platform.
B.Sc. final-year project: *Design and Implementation of an AI-Driven
Multi-Agent System for Intelligent Distributed Task Automation and Real-Time
File Synchronization Across Networked Computers.*

## How it works

```
   Web dashboard (Next.js, Vercel)
          │  HTTPS / REST + JWT (Supabase Auth)
          ▼
   Cloud backend (FastAPI, Render)
          ▲ WSS   ▲ WSS   ▲ WSS        ← agents only dial OUT — no open ports
          │       │       │
   Desktop agent (tray app on each Windows PC)
```

Agents run in the background like OneDrive: they keep an outbound WebSocket to
the backend, index the folders you share, and execute browse/search/transfer/
sync commands — no inbound ports, no command line.

## For end users (no terminal required)

1. **Sign up** on the web dashboard.
2. **Install** `NetSyncAI-Setup.exe` (or run `netsync-agent.exe` — it
   self-installs) on each computer. The app lives in the system tray and
   starts with Windows.
3. **Devices → Add this computer** → click the deep link *or* type the
   8-character code into the app's pairing window.
4. **Devices → Folders** → pick folders to share (read-only or read & write)
   with a normal directory browser.
5. **Files** → browse/download/upload/rename/tag on any connected computer.
6. **Permissions** → share a folder with a colleague (Viewer / Editor /
   Manager roles).
7. **Synchronization** → link two folders — yours, or a colleague's shared
   folder — to keep them identical in real time.

## Sharing with a colleague

Each person has their own account and pairs their own PC. To share:

- You share a folder (Devices → Folders, or Permissions → Share Folder).
- You grant the colleague by email/handle with a role on the Permissions page.
- They see the folder under Files ("shared with you") and — with the Manager
  role — can even sync it to their own PC.

Nothing is shared until you grant it; the agent on your PC is the final
authority (it never writes to a read-only folder, and system folders are
blocked outright).

## Layout

```
frontend/        Next.js dashboard (App Router, TS, Tailwind v4, lucide)
cloud_backend/   FastAPI coordination service (JWT, WSS, dispatch, AI planner)
desktop_agent/   Python Windows agent — tray app, SQLite FTS5, sync engine
shared/          Wire protocol schemas used by backend and agent
supabase/        Postgres migrations + RLS policies
installer/       Inno Setup script → NetSyncAI-Setup.exe
docs/            Architecture + deployment
```

## Development quick start

```powershell
# Backend (tests need no external services — in-memory store)
cd cloud_backend; pip install -r requirements.txt -r requirements-dev.txt
pytest; uvicorn app.main:app --reload --port 8000

# Agent (GUI dev run: python main.py --background; CLI subcommands still work)
cd desktop_agent; pip install -r requirements.txt -r requirements-dev.txt
pytest
python main.py pair ABCDEFGH --coordinator http://localhost:8000
python main.py run

# Frontend
cd frontend; npm install; copy .env.example .env.local; npm run dev
```

## Security model (short version)

- Pairing codes are short-lived, one-time, stored only as hashes.
- Device credentials are generated at pairing and hashed server-side.
- Per-folder local access (`read` / `readwrite`) is enforced on the agent —
  the coordinator cannot write a folder the agent marks read-only.
- Path traversal, symlinks/junction escapes and system folders are blocked.
- Cross-user access is path-scoped bitmask authorization, re-checked per op.

## Status

Everything in "How it works" is implemented and tested: 77 backend tests,
63 agent tests (incl. two live e2e agents over a real backend), frontend
typecheck/build, windowed PyInstaller build, Inno Setup script.

Remaining: live Supabase/Render/Vercel smoke test, code signing (SmartScreen
will warn until then), optional LAN P2P transfer (relay is used today).

See `docs/DEPLOYMENT.md` for hosting instructions.
