begin;
set local lock_timeout = '10s';
alter table public.beta_feedback
    add column status text not null default 'received'
        check (status in ('received', 'reproducing', 'fixed', 'resolved', 'on_hold')),
    add column admin_note text not null default '' check (char_length(admin_note) <= 1000),
    add column version integer not null default 1 check (version > 0),
    add column updated_at timestamptz not null default now(),
    add column updated_by uuid references auth.users(id) on delete set null;
create index beta_feedback_review_created_idx on public.beta_feedback (status, created_at desc, id desc);
alter table public.beta_feedback enable row level security;
revoke all on table public.beta_feedback from anon, authenticated;
commit;
