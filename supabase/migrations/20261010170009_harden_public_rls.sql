alter table public.users enable row level security;
alter table public.meal_logs enable row level security;
alter table public.inbody_logs enable row level security;
alter table public.diet_strategies enable row level security;
alter table public.chat_history enable row level security;
alter table public.checkpoints enable row level security;
alter table public.checkpoint_blobs enable row level security;
alter table public.checkpoint_writes enable row level security;
alter table public.checkpoint_migrations enable row level security;

revoke all on table public.users from anon, authenticated;
revoke all on table public.meal_logs from anon, authenticated;
revoke all on table public.inbody_logs from anon, authenticated;
revoke all on table public.diet_strategies from anon, authenticated;
revoke all on table public.chat_history from anon, authenticated;
revoke all on table public.checkpoints from anon, authenticated;
revoke all on table public.checkpoint_blobs from anon, authenticated;
revoke all on table public.checkpoint_writes from anon, authenticated;
revoke all on table public.checkpoint_migrations from anon, authenticated;

alter policy users_own on public.users to authenticated
    using (auth_id = (select auth.uid()))
    with check (auth_id = (select auth.uid()));
alter policy meal_own on public.meal_logs to authenticated
    using (user_id = (select id from public.users where auth_id = (select auth.uid())))
    with check (user_id = (select id from public.users where auth_id = (select auth.uid())));
alter policy inbody_own on public.inbody_logs to authenticated
    using (user_id = (select id from public.users where auth_id = (select auth.uid())))
    with check (user_id = (select id from public.users where auth_id = (select auth.uid())));
alter policy strategy_own on public.diet_strategies to authenticated
    using (user_id = (select id from public.users where auth_id = (select auth.uid())))
    with check (user_id = (select id from public.users where auth_id = (select auth.uid())));
alter policy chat_own on public.chat_history to authenticated
    using (user_id = (select id from public.users where auth_id = (select auth.uid())))
    with check (user_id = (select id from public.users where auth_id = (select auth.uid())));
