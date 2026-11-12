-- 처음 접속 튜토리얼 팝업: 계정마다 튜토리얼을 볼지 묻는 팝업에 답한 시각을 담을 열을 app_ext.user_settings 에 더한다.
-- NULL 이거나 설정 행이 없으면 아직 답하지 않은 계정이다. 이 파일은 기존 계정의 값을 채우지 않으므로 기존 계정도 답하기 전까지는 팝업 대상이다.
-- backend-setup 은 읽기 전용 검사라 이 파일을 실행하지 않는다. 이 열을 읽는 앱을 올리기 전에 DB마다 한 번 실행한다. 다시 실행해도 결과는 같다.
-- 적용(저장소 루트): docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/db/migrate_tutorial_prompt.sql
-- 복구: ALTER TABLE app_ext.user_settings DROP COLUMN IF EXISTS tutorial_answered_at;
BEGIN;

ALTER TABLE app_ext.user_settings ADD COLUMN IF NOT EXISTS tutorial_answered_at timestamptz;

COMMIT;
