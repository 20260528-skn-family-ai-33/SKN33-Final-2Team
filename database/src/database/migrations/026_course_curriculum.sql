-- Keep normalized, portable public outlines separate from immutable source/vector text.
ALTER TABLE public.courses ADD COLUMN curriculum jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.courses ADD CONSTRAINT courses_curriculum_object
    CHECK (jsonb_typeof(curriculum) = 'object');
COMMENT ON COLUMN public.courses.curriculum IS
    'Public course description and ordered outline, with source hashes and coverage; not full lesson transcripts.';
