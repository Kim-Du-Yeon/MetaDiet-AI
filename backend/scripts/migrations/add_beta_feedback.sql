create table if not exists public.beta_feedback (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    rating smallint not null check (rating between 1 and 5),
    category text not null check (
        category in ('general', 'answer_quality', 'evidence', 'usability', 'bug')
    ),
    comment text check (comment is null or char_length(comment) <= 1000),
    page text not null default 'settings' check (page = 'settings'),
    client_submission_id uuid not null,
    created_at timestamptz not null default now(),
    unique (user_id, client_submission_id)
);

create index if not exists beta_feedback_user_created_idx
    on public.beta_feedback (user_id, created_at desc);

alter table public.beta_feedback enable row level security;

comment on table public.beta_feedback is
    'Privacy-minimal beta feedback written only by the authenticated backend API.';
