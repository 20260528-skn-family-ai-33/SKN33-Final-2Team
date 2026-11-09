-- #96 결과 보고서 과제: 부서장이 결과 보고서를 보고 내는 과제와 직원의 제출 결과를 저장하고, 과제 알림을 담을 수 있게 알림 표를 넓힌다.
-- migrate_notification_rules.sql 을 먼저 적용해야 한다. backend-setup 은 읽기 전용 검사라 이 파일을 실행하지 않는다.
-- 앱을 이 버전으로 올리기 전에 DB마다 한 번 실행한다. 다시 실행해도 결과는 같고, 전체가 한 트랜잭션이라 실패하면 아무것도 바뀌지 않는다.
-- 적용(저장소 루트): docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/db/migrate_report_tasks.sql
-- 복구 방법은 backend/README.md '결과 보고서 과제 (#96)' 절에 있다.
BEGIN;

CREATE TABLE IF NOT EXISTS app_ext.report_tasks (
  task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  roadmap_id uuid NOT NULL REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE,
  employee_id integer NOT NULL REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  head_id integer NOT NULL REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  body text NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 2000),
  created_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  answer text CHECK (answer IS NULL OR length(answer) <= 4000),
  attachment jsonb,
  CONSTRAINT report_tasks_submission_check CHECK (submitted_at IS NOT NULL OR (answer IS NULL AND attachment IS NULL))
);
CREATE INDEX IF NOT EXISTS report_tasks_roadmap_idx ON app_ext.report_tasks (roadmap_id, created_at);

ALTER TABLE app_ext.notifications ADD COLUMN IF NOT EXISTS task_id uuid REFERENCES app_ext.report_tasks(task_id) ON DELETE CASCADE;
ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_kind_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ('roadmap', 'report', 'job', 'comment', 'task', 'task_result'));
ALTER TABLE app_ext.notifications DROP CONSTRAINT IF EXISTS notifications_task_check;
ALTER TABLE app_ext.notifications ADD CONSTRAINT notifications_task_check CHECK ((kind IN ('task', 'task_result')) = (task_id IS NOT NULL));

COMMIT;
