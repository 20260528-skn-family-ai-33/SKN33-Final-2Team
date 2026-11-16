-- 직원 선택 모드의 신규 설정 행에 적용한다. 기존 직원의 선택은 보존한다.
ALTER TABLE app_ext.user_settings ALTER COLUMN ai_provider SET DEFAULT 'openai';
