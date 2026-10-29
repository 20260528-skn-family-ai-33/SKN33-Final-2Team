-- GrowPath 5차 목업 · 보조 스키마 app_ext
-- 팀 ERD(public·regulations) 표는 바꾸지 않는다. ERD에 담을 곳이 없는 값만 여기에 둔다(2026-10-21 사용자 결정).
-- 같은 내용을 팀원에게 보낼 요청 목록(읽어주세요 '팀원 요청 목록')으로 정리했다. ERD에 반영되면 이 표를 옮기고 지운다.
CREATE SCHEMA IF NOT EXISTS app_ext;

-- ── 계정·권한 ──
-- 관리자 전용 계정(직원과 별개 · 사용자 결정). ERD employees 에는 관리자 역할 열이 없다
CREATE TABLE IF NOT EXISTS app_ext.admin_accounts (
  admin_id serial PRIMARY KEY,
  login_id text NOT NULL UNIQUE,
  name text NOT NULL,
  password_hash text NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- 로그인 세션(쿠키에는 무작위 토큰만, DB에는 그 해시만 둔다). 서버를 여러 대 띄워도 같은 세션을 본다(AWS 대비)
CREATE TABLE IF NOT EXISTS app_ext.sessions (
  token_hash text PRIMARY KEY,
  account_type text NOT NULL CHECK (account_type IN ('employee', 'admin')),
  account_id integer NOT NULL,
  keep_signed_in boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_account_idx ON app_ext.sessions (account_type, account_id);

-- ── 직원 인사 보조 항목 ──
-- ERD employees 에 없는 직원 구분(일반직·실무직: 규정 묶음 선택에 씀)·입사일·직위·직종·담당 업무·재직/계정 상태·직급 임용일
CREATE TABLE IF NOT EXISTS app_ext.employee_hr (
  employee_id integer PRIMARY KEY REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  employee_group text,
  hire_date date,
  position text,
  job_family text,
  task text,
  employment_status text NOT NULL DEFAULT '재직',
  account_status text NOT NULL DEFAULT 'active' CHECK (account_status IN ('active', 'locked', 'inactive')),
  grade_since date,
  valid_from date,
  change_reason text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- 본인 입력 정보(2026-10-27 팀 최신 DB 기준): 값은 팀 표(employee_input_profiles·employee_certifications·employees.unlisted_certifications)에 둔다.
-- 업무 설명은 employees.planned_project_description, 프로젝트는 employee_input_profiles.project_experience에 둔다.
-- 이 표는 입력 상태·본인 설명 변경 해시(edited: {inputStatus,workDescHash})와 처음 값(baseline: {profile,certIds,unlisted,workDesc})을 둔다.
-- 구판 edited.workDesc는 읽기 호환을 유지하고 명시적 저장/이관 때 팀 열로 옮긴다(services/profile.py).
CREATE TABLE IF NOT EXISTS app_ext.employee_self_inputs (
  employee_id integer PRIMARY KEY REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  baseline jsonb,
  edited jsonb,
  edited_at timestamptz
);
-- 근무성적평정 + 목표 추천 활용 동의(기본값과 직원이 바꾼 값)
CREATE TABLE IF NOT EXISTS app_ext.employee_evaluations (
  employee_id integer NOT NULL REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  period text NOT NULL,
  title text,
  grade text,
  score text,
  consent_default boolean NOT NULL DEFAULT false,
  consent boolean,
  consent_changed_at timestamptz,
  PRIMARY KEY (employee_id, period)
);
-- 인사이동 이력(관리자 업로드에서 부서가 바뀐 행 · 사용자 결정)
CREATE TABLE IF NOT EXISTS app_ext.employee_transfers (
  transfer_id bigserial PRIMARY KEY,
  employee_id integer NOT NULL REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  from_department_id bigint,
  to_department_id bigint,
  from_department_name text,
  to_department_name text,
  head_before boolean,
  head_after boolean,
  changed_at timestamptz NOT NULL DEFAULT now(),
  changed_by_admin integer REFERENCES app_ext.admin_accounts(admin_id),
  upload_id uuid
);

-- ── 사용자 설정 ──
-- AI 모델 모드(API-11)와 시연 도구(가데이터로 보기·생성 실패 시연). 에이전트가 서버에서 돌기 때문에 서버에 둔다
CREATE TABLE IF NOT EXISTS app_ext.user_settings (
  employee_id integer PRIMARY KEY REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  ai_provider text NOT NULL DEFAULT 'ollama' CHECK (ai_provider IN ('ollama', 'openai')),
  demo_mock boolean NOT NULL DEFAULT false,
  fail_sim jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ── 목표 후보(FR-05) 보조 ──
-- 후보 문장은 ERD public.employee_recommended_prompts(display_order 1~3)에 둔다. 추천 이유·근거 항목은 그 표에 열이 없어 여기에
CREATE TABLE IF NOT EXISTS app_ext.goal_suggestion_meta (
  employee_id integer NOT NULL REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  display_order smallint NOT NULL CHECK (display_order BETWEEN 1 AND 3),
  why text,
  basis jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (employee_id, display_order)
);
-- 직원마다 마지막 생성 상태(미리 만들기·수동 재생성). 실패해도 이전 후보는 지우지 않는다
CREATE TABLE IF NOT EXISTS app_ext.goal_suggestion_runs (
  employee_id integer PRIMARY KEY REFERENCES public.employees(employee_id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('running', 'ready', 'default', 'failed')),
  source text,
  note text,
  used jsonb NOT NULL DEFAULT '[]'::jsonb,
  profile_hash text,
  trigger text,
  error jsonb,
  job_id uuid,
  requested_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

-- ── 작업(오래 걸리는 에이전트 호출) ──
-- 화면을 떠나거나 새로 고쳐도 서버가 이어서 처리하고 결과를 남긴다(설계서 v1.7 6.2 · LangGraph 체크포인트 대신 5차는 이 표)
CREATE TABLE IF NOT EXISTS app_ext.jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id integer,
  kind text NOT NULL,
  ref text,
  status text NOT NULL CHECK (status IN ('running', 'done', 'failed', 'cancelled')),
  progress jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb,
  error jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_ref_idx ON app_ext.jobs (kind, ref);
-- 에이전트 호출 기록(NFR-06): 에이전트·작업·모드·모델·처리 시간·결과만. 입력·출력 원문과 개인정보는 남기지 않는다
CREATE TABLE IF NOT EXISTS app_ext.agent_calls (
  call_id bigserial PRIMARY KEY,
  employee_id integer,
  agent text NOT NULL,
  task text NOT NULL,
  mode text NOT NULL,
  model text,
  ms integer,
  status text NOT NULL,
  error_kind text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── 로드맵 생애주기 보조 ──
-- 상태(진행 중·마침·보관)는 ERD projects.status(IN_PROGRESS·COMPLETED·ARCHIVED)를 쓰고, 지금 버전과 상태가 바뀐 시각만 여기에
CREATE TABLE IF NOT EXISTS app_ext.roadmap_meta (
  roadmap_id uuid PRIMARY KEY REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE,
  version integer NOT NULL DEFAULT 1,
  done_at timestamptz,
  archived_at timestamptz,
  resumed_at timestamptz
);
-- 활동 진행 상태·메모·첨부 파일 이름. 완료 여부는 ERD roadmap_steps.is_completed 에도 맞춰 둔다.
-- 메모를 roadmap_steps.details 에 두지 않는 이유: 팀 DB 트리거(mark_roadmap_comments_modified)가 단계 행이 바뀌면 코멘트를
-- '수정 완료'로 바꾸는데, 코멘트 작성자 검사(guard_roadmap_comment)에 막혀 직원이 메모를 저장할 수 없게 된다
CREATE TABLE IF NOT EXISTS app_ext.activity_progress (
  roadmap_id uuid NOT NULL REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE,
  activity_id text NOT NULL,
  status text NOT NULL DEFAULT 'doing' CHECK (status IN ('doing', 'done')),
  memo text,
  attachment jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (roadmap_id, activity_id)
);
-- 결과 보고서 확인 여부. ERD growth_reports 는 트리거로 수정이 막혀 있어(guard_growth_report) 확인 표시를 여기에 둔다
CREATE TABLE IF NOT EXISTS app_ext.report_meta (
  report_id uuid PRIMARY KEY REFERENCES public.growth_reports(report_id) ON DELETE CASCADE,
  confirmed boolean NOT NULL DEFAULT false,
  confirmed_at timestamptz
);
-- 계획 버전 이력(확정·수정안 확정마다 쌓임 · 이전 버전은 지우지 않음)
CREATE TABLE IF NOT EXISTS app_ext.roadmap_versions (
  roadmap_id uuid NOT NULL REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE,
  version integer NOT NULL,
  plan jsonb NOT NULL,
  reason text,
  confirmed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (roadmap_id, version)
);
-- 수정 요청 → 수정안(API-43~45). 확정 전까지 로드맵은 그대로
CREATE TABLE IF NOT EXISTS app_ext.roadmap_revisions (
  revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  roadmap_id uuid NOT NULL REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE,
  request jsonb NOT NULL,
  result jsonb,
  status text NOT NULL CHECK (status IN ('running', 'ready', 'failed', 'accepted', 'discarded')),
  error jsonb,
  job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- 사후 점검의 목표 달성 자기평가·결과물 파일 이름(문항 응답은 ERD assessment_responses POST)
CREATE TABLE IF NOT EXISTS app_ext.post_checks (
  roadmap_id uuid PRIMARY KEY REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE,
  goal_self smallint CHECK (goal_self BETWEEN 1 AND 5),
  attachment jsonb,
  running boolean NOT NULL DEFAULT false,
  fail jsonb,
  job_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- 부서장 코멘트의 구조화 항목과 상태(새·확인함·vN에 반영). ERD roadmap_comments 에는 본문·반영 시각만 있다
CREATE TABLE IF NOT EXISTS app_ext.comment_meta (
  comment_id uuid PRIMARY KEY REFERENCES public.roadmap_comments(comment_id) ON DELETE CASCADE,
  fit text,
  fit_text text,
  level text,
  level_text text,
  free_text text,
  status text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'read', 'applied')),
  read_at timestamptz,
  applied_version integer
);

-- ── 학습 자료 보조 ──
-- 화면·에이전트가 쓰는 자료 키(강좌 course_id · 도서 book_<ISBN> · 자격 cert_<cert_id>)와 ERD 표에 없는 학습 시간·형식·단계·비용·대상 등
CREATE TABLE IF NOT EXISTS app_ext.learning_docs (
  doc_id text PRIMARY KEY,
  title text NOT NULL,
  provider text,
  url text,
  description text,
  record_source text NOT NULL DEFAULT 'mockup',
  source_verified_at timestamptz
);
CREATE TABLE IF NOT EXISTS app_ext.cert_groups (
  group_key text PRIMARY KEY,
  label text NOT NULL,
  issuer text,
  url text,
  skill_key text,
  display_order integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS app_ext.resource_meta (
  resource_key text PRIMARY KEY,
  resource_type text NOT NULL CHECK (resource_type IN ('course', 'book', 'cert', 'doc')),
  course_id varchar(50) REFERENCES public.courses(course_id) ON DELETE CASCADE,
  isbn varchar(20) REFERENCES public.books(isbn) ON DELETE CASCADE,
  cert_id integer REFERENCES public.certifications(cert_id) ON DELETE CASCADE,
  doc_id text REFERENCES app_ext.learning_docs(doc_id) ON DELETE CASCADE,
  format text,
  hours numeric(12,6),
  hours_origin text NOT NULL DEFAULT 'legacy' CONSTRAINT resource_meta_hours_origin_check CHECK (hours_origin IN ('legacy','catalog','manual')),
  stage smallint CHECK (stage BETWEEN 1 AND 4),
  cost_won integer CHECK (cost_won >= 0),
  audience text,
  prereq text,
  content text,
  note text,
  is_real boolean NOT NULL DEFAULT true,
  source_label text,
  checked_on date,
  skill_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  -- 규칙으로 채운 값(형식·시간·단계·비용 등)의 열 이름. 화면에 '추정'으로 표시하고, 관리자가 엑셀로 고치면 빠진다
  estimated_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  cert_code text,
  cert_group text REFERENCES app_ext.cert_groups(group_key),
  cert_short text,
  cert_sub text,
  cert_vendor text,
  display_order integer NOT NULL DEFAULT 0,
  CHECK (num_nonnulls(course_id, isbn, cert_id, doc_id) = 1)
);

-- Existing manual values stay distinct from source-controlled duration on setup reruns.
ALTER TABLE app_ext.resource_meta ADD COLUMN IF NOT EXISTS hours_origin text NOT NULL DEFAULT 'legacy';
ALTER TABLE app_ext.resource_meta ALTER COLUMN hours TYPE numeric(12,6);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid='app_ext.resource_meta'::regclass AND conname='resource_meta_hours_origin_check') THEN
    ALTER TABLE app_ext.resource_meta ADD CONSTRAINT resource_meta_hours_origin_check
      CHECK (hours_origin IN ('legacy','catalog','manual'));
  END IF;
END
$$;

-- ── 규정 보조 ──
-- 규정이 적용되는 직원 구분(일반직·실무직)·국외근무 전용 여부·화면 표시용 짧은 키. ERD regulations 에 열이 없다
CREATE TABLE IF NOT EXISTS app_ext.regulation_meta (
  regulation_id varchar(64) PRIMARY KEY REFERENCES regulations.regulations(regulation_id) ON DELETE CASCADE,
  short_key text NOT NULL UNIQUE,
  employee_group text NOT NULL,
  overseas_only boolean NOT NULL DEFAULT false,
  org text,
  pages integer,
  search_enabled boolean NOT NULL DEFAULT true   -- 관리자가 '도우미 검색 사용' N 으로 두면 검색·답변에서 뺀다(규정 기록은 남김)
);
ALTER TABLE app_ext.regulation_meta ADD COLUMN IF NOT EXISTS search_enabled boolean NOT NULL DEFAULT true;
-- 1536차원이 아닌 임베딩 모델의 벡터(ERD rag_chunk_embeddings 는 1536차원 고정). 2026-10-26 팀 합의로 두 모드 모두
-- text-embedding-3-small(1536)이라 보통 비어 있다 · OPENAI_EMBED_MODEL 을 다른 차원 모델로 바꿀 때만 쓰인다
CREATE TABLE IF NOT EXISTS app_ext.rag_chunk_vectors (
  rag_chunk_id varchar(64) NOT NULL REFERENCES regulations.rag_chunks(rag_chunk_id) ON DELETE CASCADE,
  embedding_model text NOT NULL,
  dimensions integer NOT NULL,
  embedding vector NOT NULL,
  input_sha256 text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (rag_chunk_id, embedding_model)
);

-- ── 관리자 업로드 기록 ──
CREATE TABLE IF NOT EXISTS app_ext.admin_uploads (
  upload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id integer REFERENCES app_ext.admin_accounts(admin_id),
  dataset text NOT NULL CHECK (dataset IN ('hr', 'regulations', 'education')),
  file_name text NOT NULL,
  status text NOT NULL CHECK (status IN ('previewed', 'applied', 'rejected', 'expired')),
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  plan jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  applied_at timestamptz
);

-- 관리자가 올린 규정 PDF(2026-10-26): 관리자는 규정을 고치지 않고 원문 PDF 만 올린다. 시스템 관리자(서비스 운영팀)가 내려받아
-- 임베딩·벡터 DB 를 갱신한다(처리 상태는 두지 않음 · 사용자 결정). 파일은 서버 폴더 var/uploads/regulations/{upload_id}.pdf
CREATE TABLE IF NOT EXISTS app_ext.regulation_uploads (
  upload_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id integer REFERENCES app_ext.admin_accounts(admin_id),
  file_name text NOT NULL,
  file_size bigint NOT NULL,
  file_sha256 text NOT NULL,
  memo text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 사후 점검 심화 질문(10/23): 같은 개념의 새 문제·답·생성 상태. 사전 심화 질문은 로드맵 content.assess.deep 에 있다
ALTER TABLE app_ext.post_checks ADD COLUMN IF NOT EXISTS deep jsonb;
