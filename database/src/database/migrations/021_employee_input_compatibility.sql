-- Restore the v2 employee-form extension after the supplied 20261026 snapshot.
-- Snapshot migrations 013-020 are preserved by recorded checksum; no HR rows change.
SET LOCAL lock_timeout = '10s';

CREATE TABLE IF NOT EXISTS public.employee_input_profiles (
    employee_id integer PRIMARY KEY REFERENCES public.employees(employee_id) ON DELETE CASCADE,
    experience_summary text,
    development_years numeric(6,2) CHECK (development_years >= 0 AND development_years <> 'NaN'::numeric),
    technology_experience text,
    project_experience text,
    learning_history text,
    learning_preferences jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(learning_preferences) = 'object'),
    submission_note text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.employee_input_profiles IS
    'Employee form extension restored after the 20261026 snapshot; original user-entered experience and preferences only.';

ALTER TABLE public.employee_input_profiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.employee_input_profiles FROM PUBLIC;
DO $access$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON public.employee_input_profiles FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON public.employee_input_profiles FROM authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.employee_input_profiles TO service_role;
    END IF;
END $access$;
NOTIFY pgrst, 'reload schema';
