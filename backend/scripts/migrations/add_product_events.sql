create table if not exists public.product_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    event_name text not null check (event_name in (
        'signup_completed', 'onboarding_started', 'onboarding_completed',
        'chat_sent', 'chat_completed', 'meal_proposed', 'meal_confirmed',
        'measurement_confirmed', 'feedback_submitted', 'error_shown'
    )),
    status text not null check (status in ('success', 'failed', 'cancelled')),
    client_event_id uuid not null,
    session_id uuid not null,
    duration_ms integer check (duration_ms is null or duration_ms between 0 and 600000),
    trace_id text check (trace_id is null or char_length(trace_id) <= 128),
    properties jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (user_id, client_event_id)
);

create index if not exists product_events_event_created_idx
    on public.product_events (event_name, created_at desc);
create index if not exists product_events_user_created_idx
    on public.product_events (user_id, created_at desc);
create index if not exists product_events_failed_created_idx
    on public.product_events (created_at desc) where status = 'failed';

alter table public.product_events enable row level security;

revoke all on table public.product_events from anon, authenticated;

comment on table public.product_events is
    'Privacy-minimal product events written and aggregated only by the backend.';

comment on table public.product_events is
    'Privacy-minimal product events. Backend service role only; no raw health or conversation content.';
