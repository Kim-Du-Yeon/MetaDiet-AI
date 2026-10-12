CREATE TABLE IF NOT EXISTS public.weight_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    measured_date DATE NOT NULL,
    weight_kg FLOAT NOT NULL CHECK (weight_kg > 0 AND weight_kg <= 500),
    source TEXT NOT NULL CHECK (source IN ('onboarding', 'manual', 'inbody')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, measured_date, source)
);

CREATE INDEX IF NOT EXISTS idx_weight_logs_user_date
    ON public.weight_logs(user_id, measured_date DESC, created_at DESC);

ALTER TABLE public.weight_logs ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.weight_logs FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.weight_logs TO authenticated, service_role;

DROP POLICY IF EXISTS weight_logs_own ON public.weight_logs;
CREATE POLICY weight_logs_own ON public.weight_logs
    FOR ALL TO authenticated
    USING (user_id IN (SELECT id FROM public.users WHERE auth_id = (SELECT auth.uid())))
    WITH CHECK (user_id IN (SELECT id FROM public.users WHERE auth_id = (SELECT auth.uid())));

INSERT INTO public.weight_logs(user_id, measured_date, weight_kg, source)
SELECT id, created_at::date, weight_kg, 'onboarding'
FROM public.users
WHERE weight_kg IS NOT NULL
ON CONFLICT (user_id, measured_date, source) DO NOTHING;
