create extension if not exists pg_trgm with schema extensions;
create table public.food_catalog_versions (
    version text primary key,
    source text not null check (source='mfds'),
    raw_sha256 text not null,
    report jsonb not null,
    verified boolean not null default false,
    active boolean not null default false,
    created_at timestamptz not null default now(),
    check (not active or verified)
);
create unique index food_catalog_one_active on public.food_catalog_versions(source) where active;
create table public.food_catalog_items (
    version text not null references public.food_catalog_versions(version),
    food_id text not null,
    normalized_name text not null,
    payload jsonb not null,
    primary key (version,food_id)
);
create index food_catalog_name_idx on public.food_catalog_items using gin(normalized_name extensions.gin_trgm_ops);
alter table public.food_catalog_versions enable row level security;
alter table public.food_catalog_items enable row level security;
revoke all on public.food_catalog_versions,public.food_catalog_items from anon,authenticated;
grant select on public.food_catalog_versions,public.food_catalog_items to service_role;
alter table public.meal_logs add column if not exists nutrition_metadata jsonb;
alter table public.meal_logs add column if not exists food_id text;
