-- #96 알림 발생 규칙: 백그라운드 작업 완료·실패(job), 부서장 코멘트(comment) 알림을 담을 수 있게 알림 표를 넓힌다.
-- backend-setup 은 읽기 전용 검사라 이 파일을 실행하지 않는다. 앱을 이 버전으로 올리기 전에 DB마다 한 번 실행한다.
-- 다시 실행해도 결과는 같다. 전체를 한 트랜잭션으로 처리하므로 중간에 실패하면 아무것도 바뀌지 않는다.
-- 적용(저장소 루트): docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/db/migrate_notification_rules.sql
-- 복구 방법은 backend/README.md '알림 발생 규칙 (#96)' 절에 있다.
BEGIN;

ALTER TABLE app_ext.notifications ADD COLUMN IF NOT EXISTS draft_id uuid REFERENCES public.projects(project_id) ON DELETE CASCADE;
ALTER TABLE app_ext.notifications ADD COLUMN IF NOT EXISTS comment_id uuid REFERENCES public.roadmap_comments(comment_id) ON DELETE CASCADE;
ALTER TABLE app_ext.notifications ADD COLUMN IF NOT EXISTS job_kind text;
ALTER TABLE app_ext.notifications ADD COLUMN IF NOT EXISTS job_status text;
-- 로드맵 확정 전 작업(3안 생성·학습 자료 준비)은 로드맵이 아직 없다
ALTER TABLE app_ext.notifications ALTER COLUMN roadmap_id DROP NOT NULL;

ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_kind_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ('roadmap', 'report', 'job', 'comment'));
ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_audience_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_audience_check CHECK (audience IN ('self', 'head', 'member'));
ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_job_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_job_check CHECK (
  (kind = 'job') = (job_kind IS NOT NULL) AND (kind = 'job') = (job_status IS NOT NULL)
  AND (job_kind IS NULL OR job_kind IN ('options', 'regenerate', 'materials', 'revision', 'report'))
  AND (job_status IS NULL OR job_status IN ('done', 'failed'))
);
ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_comment_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_comment_check CHECK ((kind = 'comment') = (comment_id IS NOT NULL));
ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_target_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_target_check CHECK (roadmap_id IS NOT NULL OR (kind = 'job' AND draft_id IS NOT NULL));

COMMIT;
