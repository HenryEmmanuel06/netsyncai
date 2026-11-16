-- Phase 4+: per-participant sync root path.
-- sync_participants.local_label is a display label; the actual synced
-- directory path lives here.
alter table public.sync_participants
  add column if not exists root_path text not null default '';
