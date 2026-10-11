create table if not exists public.agent_execution_budgets (
 user_id uuid not null references public.users(id) on delete cascade,
 run_id uuid not null,
 usage jsonb not null default '{}',
 active_since timestamptz,
 updated_at timestamptz not null default now(),
 primary key(user_id, run_id)
);
alter table public.agent_execution_budgets enable row level security;
revoke all on public.agent_execution_budgets from anon, authenticated;
grant all on public.agent_execution_budgets to service_role;
