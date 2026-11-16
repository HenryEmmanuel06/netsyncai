# NetSync AI

AI-driven multi-agent distributed file management and synchronization platform.
B.Sc. final-year project: *Design and Implementation of an AI-Driven
Multi-Agent System for Intelligent Distributed Task Automation and Real-Time
File Synchronization Across Networked Computers.*

**Status: Phase 1 — Foundation.** See `docs/ARCHITECTURE.md` for the full
design and the roadmap, and "Limitations" below for what is not built yet.

## Layout

```
frontend/        Next.js (App Router, TS, Tailwind) + Supabase Auth
cloud_backend/   FastAPI coordination service (Render target)
desktop_agent/   Python Windows agent (SQLite FTS5, watchdog-ready)
shared/          Wire protocol schemas used by backend and agent
supabase/        Postgres migrations + RLS policies
installer/       Inno Setup script (Phase 6)
docs/            Architecture and decisions
.github/         CI workflows
```

## Quick start

### Cloud backend

```powershell
cd cloud_backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env   # fill in values
pytest                   # tests run with no external services
uvicorn app.main:app --reload --port 8000
```

### Desktop agent

```powershell
cd desktop_agent
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pytest
python main.py init
python main.py pair ABCDEFGH --coordinator http://localhost:8000   # code from Devices page
python main.py run          # daemon: persistent WSS + heartbeats + reconnect
```

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local   # Supabase project URL + anon key
npm run dev
```

## Environment variables

See each component's `.env.example`. Never commit real secrets. The desktop
agent never ships service-role keys — pairing uses short-lived codes.

## Supabase

Apply migrations in order under `supabase/migrations/` (e.g. via
`supabase db push` or the SQL editor). All tables have RLS enabled.

## Limitations (Phase 1)

Implemented and tested: monorepo, DB schema + RLS, backend health/auth/JWT,
device registry, pairing codes + agent WebSocket + live presence (Phase 2),
**remote file management** (Phase 3): browse/search/rename/move/copy/mkdir/
delete dispatched over WSS with agent-side path security + per-folder
access levels, chunked base64 transfers with SHA-256 verification + atomic
writes + collision renaming, Network Files UI.

Transfer transport is currently the coordinator relay (works through any
NAT); direct LAN P2P is designed but deferred.

Not yet implemented: multi-user permission grants UI, sync engine, AI task
planning, document conversion, tray UI, installer build, deployments.
