ALTER TABLE public.courses
    DROP CONSTRAINT chk_courses_difficulty,
    ADD CONSTRAINT chk_courses_difficulty CHECK (
        difficulty IN ('BEGINNER', 'INTERMEDIATE', 'UPPER_INTERMEDIATE', 'ADVANCED')
    );
