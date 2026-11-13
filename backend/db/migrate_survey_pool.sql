-- #225 진단 설문 사전 생성 풀: 스킬 태그마다 5점 자기평가 문항 5개를 미리 저장해 두고, 진단 요청 때 모델 생성 없이 읽는다.
-- 앱을 이 버전으로 올리기 전에 DB마다 한 번 실행한다. 다시 실행해도 결과는 같고, 전체가 한 트랜잭션이라 실패하면 아무것도 바뀌지 않는다.
-- 적용(저장소 루트): docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backend/db/migrate_survey_pool.sql
-- 문항 채우기: backend/tools/generate_survey_pool.py (옵션 없이 실행하면 읽기 전용 점검만 한다)
-- 복구: DROP TABLE app_ext.skill_survey_pool; 표가 없거나 스킬 문항이 비어 있으면 앱은 이전처럼 모델로 설문을 만든다.
BEGIN;

CREATE TABLE IF NOT EXISTS app_ext.skill_survey_pool (
  skill_id integer PRIMARY KEY REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE,
  skill_name varchar(50) NOT NULL,
  title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
  surveys jsonb NOT NULL CHECK (jsonb_typeof(surveys) = 'array' AND jsonb_array_length(surveys) = 5),
  model text NOT NULL,
  prompt_hash char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
