create table if not exists public.account_deletion_tombstones (
    auth_id_hash text primary key check (length(auth_id_hash) = 64),
    created_at timestamptz not null default now()
);

alter table public.account_deletion_tombstones enable row level security;
revoke all on public.account_deletion_tombstones from anon, authenticated;
