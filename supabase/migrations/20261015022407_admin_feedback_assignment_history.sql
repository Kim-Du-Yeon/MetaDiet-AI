begin;
set local lock_timeout = '10s';
alter table public.beta_feedback add column assignee_id uuid references auth.users(id) on delete set null;
create table public.beta_feedback_history (
 id uuid primary key default gen_random_uuid(),
 feedback_id uuid not null references public.beta_feedback(id) on delete cascade,
 version integer not null check(version>1),
 actor_auth_id uuid references auth.users(id) on delete set null,
 created_at timestamptz not null default now(),
 before_status text not null,
 after_status text not null,
 before_note text not null check(length(before_note)<=1000),
 after_note text not null check(length(after_note)<=1000),
 before_assignee_id uuid,
 after_assignee_id uuid,
 unique(feedback_id,version)
);
alter table public.beta_feedback_history enable row level security;
revoke all on table public.beta_feedback_history from anon, authenticated;
commit;
