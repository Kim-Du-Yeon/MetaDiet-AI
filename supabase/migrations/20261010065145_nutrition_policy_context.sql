-- Additive only. Applicability is self-reported; NULL remains unknown.
alter table public.users add column if not exists nutrition_policy_context jsonb;
comment on column public.users.nutrition_policy_context is
  'Explicit EER inputs and self-reported general-adult applicability; not clinical clearance';
