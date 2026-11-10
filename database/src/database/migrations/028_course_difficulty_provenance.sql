ALTER TABLE public.courses
    ADD COLUMN difficulty_estimated boolean NOT NULL DEFAULT false,
    ADD COLUMN difficulty_basis text,
    ADD CONSTRAINT chk_courses_difficulty_estimate CHECK (
        NOT difficulty_estimated OR
        (difficulty IS NOT NULL AND nullif(btrim(difficulty_basis), '') IS NOT NULL)
    );

-- A manual edit or source correction supersedes the old justification.
CREATE FUNCTION public.clear_changed_course_difficulty_basis() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.difficulty IS DISTINCT FROM NEW.difficulty
       AND NEW.difficulty_basis IS NOT DISTINCT FROM OLD.difficulty_basis
       AND NEW.difficulty_estimated = OLD.difficulty_estimated THEN
        NEW.difficulty_estimated := false;
        NEW.difficulty_basis := NULL;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER course_difficulty_basis_on_change
    BEFORE UPDATE OF difficulty ON public.courses
    FOR EACH ROW EXECUTE FUNCTION public.clear_changed_course_difficulty_basis();
