-- Additive schema. Domain writes are performed in one server-side transaction.
create table if not exists public.agent_proposals (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  thread_id text not null,
  version integer not null check (version > 0),
  kind text not null check (kind in ('intake','plan','measurement','strategy','meal_delete','meal_replace')),
  payload jsonb not null,
  status text not null default 'pending' check (status in ('pending','confirmed','cancelled','superseded')),
  dedupe_key text not null,
  result jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '24 hours',
  resolved_at timestamptz,
  unique(user_id, dedupe_key)
);
create index if not exists agent_proposals_thread on public.agent_proposals(user_id, thread_id, created_at desc);
create table if not exists public.meal_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  proposal_id uuid not null unique references public.agent_proposals(id),
  plan_date date not null,
  meals jsonb not null,
  created_at timestamptz not null default now()
);
create table if not exists public.strategy_versions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  proposal_id uuid not null unique references public.agent_proposals(id),
  strategy_id uuid not null references public.diet_strategies(id),
  version integer not null,
  evidence jsonb not null,
  policy_version text not null,
  effective_date date not null,
  created_at timestamptz not null default now(),
  unique(user_id, version)
);
alter table public.agent_proposals enable row level security;
alter table public.meal_plans enable row level security;
alter table public.strategy_versions enable row level security;
-- Only the authenticated backend writes. Clients cannot self-approve via REST.
revoke all on public.agent_proposals, public.meal_plans, public.strategy_versions from anon, authenticated;
grant all on public.agent_proposals, public.meal_plans, public.strategy_versions to service_role;
