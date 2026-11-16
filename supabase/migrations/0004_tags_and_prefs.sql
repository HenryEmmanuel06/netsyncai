-- File tags: personal labels on remote paths (each user tags what they see).

create table if not exists public.file_tags (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles(id) on delete cascade,
  device_id  uuid not null references public.devices(id) on delete cascade,
  path       text not null,
  tag        text not null,
  created_at timestamptz not null default now(),
  unique (user_id, device_id, path, tag)
);
create index if not exists file_tags_user_idx
  on public.file_tags (user_id, device_id);
