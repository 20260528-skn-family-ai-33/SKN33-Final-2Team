-- 비어 있는 테스트 DB에서 psql -f 로 실행한다.
\set ON_ERROR_STOP on
CREATE SCHEMA app_ext;
CREATE TABLE app_ext.user_settings (
  employee_id integer PRIMARY KEY,
  ai_provider text NOT NULL DEFAULT 'ollama',
  reasoning jsonb,
  demo_mock boolean,
  tutorial_answered_at timestamptz
);
INSERT INTO app_ext.user_settings (employee_id, ai_provider, reasoning, demo_mock, tutorial_answered_at)
VALUES (1, DEFAULT, '{"openai":"low"}', true, now()),
       (2, 'ollama', NULL, false, NULL),
       (3, 'openai', NULL, false, NULL);
CREATE TEMP TABLE other_settings AS
SELECT employee_id, to_jsonb(s) - 'ai_provider' AS settings FROM app_ext.user_settings s;

-- 기본값만 바꾼 앞선 SQL을 이미 적용한 배포도 기존 직원의 값을 초기화해야 한다.
\if :{?default_already_openai}
\ir ../db/migrate_employee_provider_default.sql
\endif
\ir ../db/migrate_reset_employee_providers.sql
INSERT INTO app_ext.user_settings (employee_id) VALUES (4);
DO $$
BEGIN
  IF (SELECT count(*) FROM app_ext.user_settings WHERE ai_provider = 'openai') <> 4 THEN
    RAISE EXCEPTION 'Expected existing employees and the new employee to use OpenAI';
  END IF;
  IF EXISTS (SELECT employee_id, settings FROM other_settings
             EXCEPT SELECT employee_id, to_jsonb(s) - 'ai_provider' FROM app_ext.user_settings s) THEN
    RAISE EXCEPTION 'Employee settings other than the provider changed';
  END IF;
END $$;

UPDATE app_ext.user_settings SET ai_provider = 'ollama' WHERE employee_id = 2;
\ir ../db/migrate_reset_employee_providers.sql
DO $$
BEGIN
  IF (SELECT ai_provider FROM app_ext.user_settings WHERE employee_id = 2) IS DISTINCT FROM 'ollama' THEN
    RAISE EXCEPTION 'Reapplying the migration overwrote a later RunPod selection';
  END IF;
END $$;
