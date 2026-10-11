alter table public.chat_history
    add column if not exists thread_id text;

update public.chat_history
set thread_id = 'legacy'
where thread_id is null or btrim(thread_id) = '';

alter table public.chat_history
    alter column thread_id set default 'default',
    alter column thread_id set not null;

create index if not exists idx_chat_history_user_thread
    on public.chat_history(user_id, thread_id, created_at desc);
