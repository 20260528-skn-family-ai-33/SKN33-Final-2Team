-- #296 배포 전에 실행한다. 기존 RunPod 선택 초기화와 이력 기록을 한 트랜잭션으로 처리한다.
BEGIN;

ALTER TABLE app_ext.user_settings ALTER COLUMN ai_provider SET DEFAULT 'openai';
CREATE TABLE IF NOT EXISTS app_ext.data_migrations (
  name text PRIMARY KEY
);

WITH first_run AS (
  INSERT INTO app_ext.data_migrations (name) VALUES ('296_reset_employee_providers')
  ON CONFLICT (name) DO NOTHING
  RETURNING name
)
UPDATE app_ext.user_settings SET ai_provider = 'openai'
WHERE ai_provider = 'ollama' AND EXISTS (SELECT 1 FROM first_run);

COMMIT;
