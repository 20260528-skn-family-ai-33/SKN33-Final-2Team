-- Source duration and curriculum-based planning estimates have distinct storage.
ALTER TABLE public.courses
 ADD COLUMN IF NOT EXISTS duration_seconds integer,
 ADD COLUMN IF NOT EXISTS duration_kind text,
 ADD COLUMN IF NOT EXISTS estimated_duration_seconds integer,
 ADD COLUMN IF NOT EXISTS duration_provenance jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.courses ADD CONSTRAINT courses_duration_seconds_positive
 CHECK (duration_seconds IS NULL OR duration_seconds > 0);
ALTER TABLE public.courses ADD CONSTRAINT courses_estimated_duration_seconds_positive
 CHECK (estimated_duration_seconds IS NULL OR estimated_duration_seconds > 0);
ALTER TABLE public.courses ADD CONSTRAINT courses_duration_kind_valid
 CHECK (((duration_seconds IS NULL AND duration_kind IS NULL)
     OR (duration_seconds IS NOT NULL AND duration_kind IN ('video','learning'))) IS TRUE);
ALTER TABLE public.courses ADD CONSTRAINT courses_duration_provenance_object
 CHECK (jsonb_typeof(duration_provenance)='object');
COMMENT ON COLUMN public.courses.duration_seconds IS '제공처에서 확인한 영상 또는 학습 총시간(초). 미확인은 NULL이며 계획 추정과 구분.';
COMMENT ON COLUMN public.courses.duration_kind IS 'video=영상 재생시간, learning=제공처 학습/학습인정시간.';
COMMENT ON COLUMN public.courses.estimated_duration_seconds IS '총시간 미확보 시 공개 영상 차시 수 × 기준시간으로 계산한 로드맵 계획 추정(초).';
COMMENT ON COLUMN public.courses.duration_provenance IS '출처 URL/필드/원본 해시/수집 시각, 영상 누락 여부와 계획 추정 산식. 실제 이수시간이 아님.';
