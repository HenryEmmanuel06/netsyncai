-- Sync requests can be addressed to a user (email/handle/id) before they
-- choose which of their folders receives the sync. The session stays
-- 'pending' until the recipient accepts and their participant row is added.
alter table public.sync_sessions
  add column if not exists pending_user_id uuid references public.profiles(id);

create index if not exists sync_sessions_pending_user_idx
  on public.sync_sessions (pending_user_id);
