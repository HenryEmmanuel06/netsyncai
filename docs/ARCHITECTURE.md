# NetSync AI — Architecture & Design

> Status: Living document. Sections marked **[implemented]** exist in code; everything else is the agreed design contract for later phases.

## 1. System Overview

NetSync AI is a three-tier distributed system:

```
┌──────────────┐   HTTPS/WSS   ┌───────────────────┐   WSS (agent-initiated)  ┌──────────────┐
│  Next.js Web │ ◄───────────► │  FastAPI Cloud    │ ◄──────────────────────► │ Desktop Agent│
│  (Vercel)    │               │  Coordinator      │                          │ (Windows)    │
└──────────────┘               │  (Render)         │                          └──────┬───────┘
        │                      └─────────┬─────────┘                                 │
        │  Supabase Auth (JWT)           │                                           │ LAN P2P
        └──────────────┬─────────────────┘                                           │ file transfer
                       ▼                                                             ▼
              ┌─────────────────┐                                          ┌──────────────────┐
              │ Supabase        │                                          │  Peer Agent      │
              │ Postgres + Auth │                                          │  (LAN/relay)     │
              └─────────────────┘                                          └──────────────────┘
```

**Key invariant:** user file contents live on user devices or move directly
device→device. The cloud coordinator stores metadata, permissions, task state,
and audit logs — never bulk user files.

## 2. Component Responsibilities

### 2.1 Frontend (Next.js, Vercel)
- Supabase Auth UX: register, verify email, login, password recovery.
- AI Assistant prompt UI with `@` mention autocomplete.
- Network file explorer (own + permitted remote folders).
- Device, permission, sync, transfer, activity dashboards.
- Talks to: Supabase Auth (direct), Cloud Backend (REST + WSS with Bearer JWT).
- Never holds service-role keys; never assumes files are in Supabase.

### 2.2 Cloud Backend (FastAPI, Render)
- Verifies Supabase JWTs (HS256 legacy secret or asymmetric JWKS).
- Device registry, pairing-code lifecycle, presence, revocation.
- WebSocket hub for agents (`/ws/agent`) and browsers (`/ws/client`).
- Permission *coordination* (records and routes decisions; the owning agent
  makes the final local authorization decision).
- Task engine: AI plans → validated steps → dispatch to agents → track.
- Transfer signaling: brokers handshake, capability exchange, and (Phase 4+)
  relayed metadata; LAN payload goes peer-to-peer.
- Audit logging to Postgres. All durable state in Postgres — in-memory state
  is treated as a cache only, so restarts recover cleanly.

### 2.3 Desktop Agent (Windows, Python)
- Registers/pairs via short-lived code; stores a scoped device credential.
- Maintains outbound WSS to the coordinator (auto-reconnect, heartbeat).
- Local SQLite (FTS5) index of *explicitly selected* folders only.
- Watchdog change detection → sync journal → propagation (Phase 4).
- File-transfer server/client for LAN peers, chunked + SHA-256 (Phase 3).
- LibreOffice headless conversion in isolated temp dirs (Phase 6).
- **Final authority** on all local file operations: validates permissions,
  resolves paths against allowed roots, blocks traversal/symlink escapes.
- System tray UI; runs without a browser.

## 3. Communication Protocols

| Link | Transport | Auth | Purpose |
|---|---|---|---|
| Browser → Cloud | HTTPS REST + WSS | Supabase JWT (Bearer / `?token=`) | CRUD, commands, live task/presence updates |
| Agent → Cloud | WSS (outbound 443) | Device credential obtained via pairing | Commands in, results/presence out — NAT-friendly, no inbound ports |
| Browser → Supabase | HTTPS | anon key | Auth flows only |
| Agent ↔ Agent (LAN) | HTTPS/mTLS-ish pinned TLS over TCP | Per-transfer ticket signed by coordinator | Chunked file payloads |
| Agent ↔ Agent (WAN, later) | Encrypted relay via coordinator | Same tickets | Fallback when no LAN route |

**Why agent-initiated WSS:** agents behind NAT can't accept inbound
connections from the cloud; one outbound 443 socket works everywhere and also
carries presence heartbeats.

**Envelope** (all WSS messages, see `shared/protocol/`):

```json
{ "v": 1, "id": "uuid", "type": "command.dispatch|command.result|presence.update|…",
  "ts": 1234567890, "payload": { … } }
```

## 4. Database Schema (Postgres/Supabase)

Full DDL in `supabase/migrations/0001_initial_schema.sql`. Summary:

- `profiles` — mirrors `auth.users`, display name, discovery opt-in.
- `devices` — per-user machines; `name`, `platform`, `status`, `revoked_at`.
- `device_sessions` — active agent connections (heartbeat, agent version).
- `device_pairing_requests` — short-lived, single-use, SHA-256-hashed codes.
- `shared_folders` — owner + device + label + server-side path hint (opaque
  to other users; real path stays on the agent).
- `folder_permissions` — subject (user or device) × folder × role
  (`viewer|editor|manager`) × granular permission bit set.
- `access_requests`, `blocked_users`, `blocked_devices`.
- `sync_sessions`, `sync_participants` — direction, mode (`live|review`), state.
- `tasks`, `task_steps` — AI/manual operation plans and per-step status.
- `transfer_sessions` — negotiated transfers, checksums, state.
- `activity_logs` — append-only audit trail.

RLS: every table is RLS-enabled. Policies key on `auth.uid()`; devices/
permissions rows are visible to owners and explicitly-granted subjects only.

**Agent-local SQLite** (`desktop_agent/database/schema.sql`): `indexed_files`
(FTS5), `indexed_folders`, `local_permissions`, `file_revisions`,
`sync_journal`, `pending_operations`, `transfer_checkpoints`, `agent_settings`.

## 5. Remote Connectivity & File Transfer

1. **Handshake via coordinator:** requester → `POST /transfers` → coordinator
   checks permissions, creates `transfer_session`, signs a short-lived ticket
   containing `{transfer_id, sha256, size, allowed_path_prefix}`.
2. **Route selection:** agents exchange candidates — LAN address (from agent
   hello) first; relay fallback later. `Transport` is an interface so QUIC/
   WebRTC/relay can be added without touching the transfer engine.
3. **Payload:** chunked (64 KiB+) over TLS; receiver writes to
   `<dest>/.netsync-partial/<id>.part`, verifies SHA-256, then atomic rename.
   `transfer_checkpoints` allow resume after interruption.
4. **Receiver-side authorization:** even with a valid ticket, the receiving
   agent re-validates the destination against its own `local_permissions`
   and allowed roots before writing a byte.

## 6. Security Model (Phase-1-critical decisions)

- No service-role or shared admin credentials in the desktop binary — pairing
  codes only; the coordinator mints scoped device credentials.
- All path handling goes through one `safe_resolve()` helper (agent).
- LLM output is validated against strict tool schemas; it can only *select*
  predefined operations, never emit shell or paths outside resolved entities.
- Local agent wins on any local authorization question (defense in depth:
  coordinator policy checks + agent re-check).

## 7. Technical Risks

| Risk | Mitigation |
|---|---|
| NAT traversal for WAN P2P | Phase-1 scope = LAN; `Transport` abstraction + relay fallback designed in from day one |
| Sync loops (A→B→A) | Stable op-IDs in `sync_journal`; skip ops we've already applied/seen |
| Conflict data loss | Never silent-overwrite: keep `.conflict-<dev>-<ts>` copies + resolution UI |
| Supabase JWT variants (HS256 vs ES256 JWKS) | Verifier supports both, auto-selects |
| Render restarts losing tasks | All task/session state in Postgres; agents re-register on reconnect |
| Pairing code interception | Short TTL, single-use, hashed at rest, shown only to the signed-in owner |
| Path traversal / symlink escape | `safe_resolve` + deny-by-default roots + tests for `..`, junctions, UNC |
| LLM producing invalid plans | Strict JSON-schema validation + dry-run + human authorization for destructive ops |

## 8. Phased Plan & Acceptance Criteria

| Phase | Deliverable | Acceptance |
|---|---|---|
| **1 Foundation** *(this PR)* | Monorepo, migrations, FastAPI health+auth+device registry, agent SQLite/FTS5+path security, Next.js auth shell | `pytest` green on backend & agent; `next build` green; migrations parse |
| 2 Connectivity | Pairing flow, agent WSS, presence | Two agents on one machine pair and show Online in dashboard |
| 3 File mgmt | Indexing, browse/search, LAN transfer | Unauthorized rename/path-traversal tests fail closed; chunked transfer with resume passes |
| 4 Sync | Watchdog, bidirectional sync, conflicts | Two agents sync a folder; simultaneous edit produces conflict copies, no data loss |
| 5 AI | Gemini tool-calling → task engine | Golden prompt suite ≥ threshold accuracy; destructive ops require approval |
| 6 Packaging | PyInstaller + Inno + tray | Clean install/uninstall on Windows; agent survives reboot |
| 7 Deploy & eval | Vercel/Render/Releases + metrics | Reproducible experiment scripts; no fabricated results |

## 9. What Phase 1 Deliberately Does *Not* Do

Real pairing, WSS, presence, remote browsing, transfers, sync, AI calls,
tray, and packaging are scaffolded or designed but **not implemented** — see
README "Limitations".
