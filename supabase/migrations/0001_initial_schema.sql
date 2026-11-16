-- NetSync AI — initial schema
-- All tables are RLS-enabled. Owners manage their rows; subjects see only
-- rows explicitly granted to them. Run via `supabase db push` or SQL editor.

create extension if not exists "pgcrypto";

-- ─── enums ─────────────────────────────────────────────────────────────────
create type device_status as enum ('online', 'busy', 'invisible', 'offline');
create type permission_role as enum ('viewer', 'editor', 'manager', 'private');
create type access_request_status as enum ('pending', 'approved', 'denied', 'expired');
create type sync_mode as enum ('live', 'review');
create type sync_state as enum ('pending', 'active', 'paused', 'stopped', 'error');
create type task_status as enum ('pending', 'awaiting_approval', 'running', 'succeeded', 'failed', 'cancelled');
create type transfer_state as enum ('requested', 'negotiating', 'active', 'paused', 'completed', 'failed', 'cancelled');

-- ─── profiles ───────────────────────────────────────────────────────────────
create table public.profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  email         text not null,
  display_name  text not null default '',
  handle        text unique,               -- @mention handle, e.g. 'aje'
  discoverable  boolean not null default false,  -- discovery is opt-in
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, coalesce(new.email, ''), coalesce(new.raw_user_meta_data->>'display_name', ''));
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ─── devices ────────────────────────────────────────────────────────────────
create table public.devices (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null references public.profiles(id) on delete cascade,
  name            text not null,
  platform        text not null default 'windows',
  agent_version   text,
  status          device_status not null default 'offline',
  public_key      bytea,                    -- device credential fingerprint
  last_seen_at    timestamptz,
  revoked_at      timestamptz,              -- non-null => device revoked
  created_at      timestamptz not null default now(),
  unique (owner_id, name)
);
create index devices_owner_idx on public.devices (owner_id);
create index devices_status_idx on public.devices (status) where revoked_at is null;

create table public.device_sessions (
  id           uuid primary key default gen_random_uuid(),
  device_id    uuid not null references public.devices(id) on delete cascade,
  connected_at timestamptz not null default now(),
  disconnected_at timestamptz,
  last_heartbeat_at timestamptz,
  agent_version text,
  lan_address  inet,                        -- advertised LAN endpoint
  lan_port     integer
);
create index device_sessions_device_idx on public.device_sessions (device_id, connected_at desc);

create table public.device_pairing_requests (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null references public.profiles(id) on delete cascade,
  code_hash    bytea not null unique,       -- SHA-256 of the pairing code; raw code never stored
  device_name  text not null,
  expires_at   timestamptz not null,
  used_at      timestamptz,                 -- non-null => consumed (single use)
  created_at   timestamptz not null default now()
);
create index pairing_expiry_idx on public.device_pairing_requests (expires_at) where used_at is null;

-- ─── sharing & permissions ──────────────────────────────────────────────────
create table public.shared_folders (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null references public.profiles(id) on delete cascade,
  device_id    uuid not null references public.devices(id) on delete cascade,
  label        text not null,               -- shown to collaborators
  path_hint    text not null,               -- opaque server-side; real path lives on the agent
  created_at   timestamptz not null default now()
);
create index shared_folders_device_idx on public.shared_folders (device_id);

-- granular permission bits (stored in permissions_granted int)
-- 1 browse | 2 download | 4 upload | 8 rename | 16 edit | 32 move
-- 64 delete | 128 create_folder | 256 start_sync | 512 manage_sync | 1024 manage_sharing
create table public.folder_permissions (
  id                  uuid primary key default gen_random_uuid(),
  folder_id           uuid not null references public.shared_folders(id) on delete cascade,
  subject_user_id     uuid references public.profiles(id) on delete cascade,
  subject_device_id   uuid references public.devices(id) on delete cascade,
  role                permission_role not null default 'viewer',
  permissions_granted integer not null default 0,
  granted_by          uuid not null references public.profiles(id),
  created_at          timestamptz not null default now(),
  check (subject_user_id is not null or subject_device_id is not null)
);
create index folder_permissions_subject_idx
  on public.folder_permissions (subject_user_id, subject_device_id);

create table public.access_requests (
  id           uuid primary key default gen_random_uuid(),
  requester_id uuid not null references public.profiles(id) on delete cascade,
  folder_id    uuid not null references public.shared_folders(id) on delete cascade,
  role         permission_role not null default 'viewer',
  status       access_request_status not null default 'pending',
  created_at   timestamptz not null default now(),
  resolved_at  timestamptz
);

create table public.blocked_users (
  blocker_id uuid not null references public.profiles(id) on delete cascade,
  blocked_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_id),
  check (blocker_id <> blocked_id)
);

create table public.blocked_devices (
  blocker_id uuid not null references public.profiles(id) on delete cascade,
  device_id  uuid not null references public.devices(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, device_id)
);

-- ─── synchronization ────────────────────────────────────────────────────────
create table public.sync_sessions (
  id           uuid primary key default gen_random_uuid(),
  name         text not null default '',
  mode         sync_mode not null default 'live',
  state        sync_state not null default 'pending',
  created_by   uuid not null references public.profiles(id),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table public.sync_participants (
  id             uuid primary key default gen_random_uuid(),
  session_id     uuid not null references public.sync_sessions(id) on delete cascade,
  device_id      uuid not null references public.devices(id) on delete cascade,
  folder_id      uuid references public.shared_folders(id) on delete set null,
  local_label    text not null default '',
  role           permission_role not null default 'editor',
  last_synced_at timestamptz,
  unique (session_id, device_id)
);

-- ─── tasks (AI + manual operations share this engine) ───────────────────────
create table public.tasks (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null references public.profiles(id) on delete cascade,
  kind         text not null,               -- search_files | download_file | start_sync | …
  status       task_status not null default 'pending',
  prompt       text,                        -- original NL prompt, if AI-driven
  plan         jsonb,                       -- validated structured plan
  error        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index tasks_owner_idx on public.tasks (owner_id, created_at desc);

create table public.task_steps (
  id           uuid primary key default gen_random_uuid(),
  task_id      uuid not null references public.tasks(id) on delete cascade,
  seq          integer not null,
  tool         text not null,
  args         jsonb not null default '{}',
  status       task_status not null default 'pending',
  result       jsonb,
  unique (task_id, seq)
);

-- ─── transfers ──────────────────────────────────────────────────────────────
create table public.transfer_sessions (
  id               uuid primary key default gen_random_uuid(),
  task_id          uuid references public.tasks(id) on delete set null,
  source_device_id uuid not null references public.devices(id),
  dest_device_id   uuid not null references public.devices(id),
  source_path_hint text not null,
  dest_path_hint   text not null,
  file_size        bigint,
  sha256           bytea,
  state            transfer_state not null default 'requested',
  bytes_sent       bigint not null default 0,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- ─── audit ──────────────────────────────────────────────────────────────────
create table public.activity_logs (
  id         bigint generated always as identity primary key,
  actor_id   uuid references public.profiles(id) on delete set null,
  device_id  uuid references public.devices(id) on delete set null,
  action     text not null,                 -- e.g. 'folder.shared', 'transfer.completed'
  target     text,
  metadata   jsonb not null default '{}',
  created_at timestamptz not null default now()
);
create index activity_logs_actor_idx on public.activity_logs (actor_id, created_at desc);

-- ─── updated_at trigger ─────────────────────────────────────────────────────
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

create trigger touch_profiles  before update on public.profiles        for each row execute function public.touch_updated_at();
create trigger touch_sync      before update on public.sync_sessions   for each row execute function public.touch_updated_at();
create trigger touch_tasks     before update on public.tasks           for each row execute function public.touch_updated_at();
create trigger touch_transfers before update on public.transfer_sessions for each row execute function public.touch_updated_at();

-- ─── Row-Level Security ─────────────────────────────────────────────────────
alter table public.profiles                enable row level security;
alter table public.devices                 enable row level security;
alter table public.device_sessions         enable row level security;
alter table public.device_pairing_requests enable row level security;
alter table public.shared_folders          enable row level security;
alter table public.folder_permissions      enable row level security;
alter table public.access_requests         enable row level security;
alter table public.blocked_users           enable row level security;
alter table public.blocked_devices         enable row level security;
alter table public.sync_sessions           enable row level security;
alter table public.sync_participants       enable row level security;
alter table public.tasks                   enable row level security;
alter table public.task_steps              enable row level security;
alter table public.transfer_sessions       enable row level security;
alter table public.activity_logs           enable row level security;

-- profiles: self full access; others may read only discoverable profiles
create policy profiles_self on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);
create policy profiles_discoverable_read on public.profiles
  for select using (discoverable = true);

-- devices: owner only
create policy devices_owner on public.devices
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy device_sessions_owner on public.device_sessions
  for all using (exists (select 1 from public.devices d
    where d.id = device_id and d.owner_id = auth.uid()));

create policy pairing_owner on public.device_pairing_requests
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

-- shared folders: owner manages; subjects may select folders they can see
create policy shared_folders_owner on public.shared_folders
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);
create policy shared_folders_subject_read on public.shared_folders
  for select using (exists (select 1 from public.folder_permissions p
    where p.folder_id = id and p.subject_user_id = auth.uid()));

-- permissions: folder owner manages; subject can read own grants
create policy folder_permissions_owner on public.folder_permissions
  for all using (exists (select 1 from public.shared_folders f
    where f.id = folder_id and f.owner_id = auth.uid()));
create policy folder_permissions_subject_read on public.folder_permissions
  for select using (subject_user_id = auth.uid());

create policy access_requests_mine on public.access_requests
  for all using (auth.uid() = requester_id or exists
    (select 1 from public.shared_folders f where f.id = folder_id and f.owner_id = auth.uid()));

create policy blocked_users_self on public.blocked_users
  for all using (auth.uid() = blocker_id) with check (auth.uid() = blocker_id);
create policy blocked_devices_self on public.blocked_devices
  for all using (auth.uid() = blocker_id) with check (auth.uid() = blocker_id);

create policy sync_sessions_participant on public.sync_sessions
  for all using (auth.uid() = created_by or exists
    (select 1 from public.sync_participants sp
      join public.devices d on d.id = sp.device_id
      where sp.session_id = id and d.owner_id = auth.uid()));
create policy sync_participants_owner on public.sync_participants
  for all using (exists (select 1 from public.devices d
    where d.id = device_id and d.owner_id = auth.uid()));

create policy tasks_owner on public.tasks
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);
create policy task_steps_owner on public.task_steps
  for all using (exists (select 1 from public.tasks t
    where t.id = task_id and t.owner_id = auth.uid()));

create policy transfer_sessions_party on public.transfer_sessions
  for all using (exists (select 1 from public.devices d
    where d.owner_id = auth.uid()
      and (d.id = source_device_id or d.id = dest_device_id)));

create policy activity_logs_actor on public.activity_logs
  for select using (auth.uid() = actor_id);
create policy activity_logs_insert on public.activity_logs
  for insert with check (auth.uid() = actor_id);
