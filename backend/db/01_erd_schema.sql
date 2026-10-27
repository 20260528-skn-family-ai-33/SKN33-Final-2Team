-- GrowPath 5차 목업 · 팀 ERD 최종본(2026-10-21 받은 파일)에서 만든 표 정의. 손으로 고치지 말고 tools/gen_schema.py 로 다시 만든다.
-- public·regulations 스키마만 만든다(growpath_legacy·growpath_meta 제외). 앱 전용 보조 표는 02_app_ext.sql.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS regulations;
CREATE SEQUENCE IF NOT EXISTS public.certifications_cert_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.skill_tags_skill_id_seq;
CREATE SEQUENCE IF NOT EXISTS public.users_user_id_seq;

-- 설문 문항 (팀원 DB 행 수 25)
CREATE TABLE IF NOT EXISTS public.assessment_questions (
  question_id uuid DEFAULT gen_random_uuid() NOT NULL,
  project_id uuid NOT NULL,
  assessment_type character varying(20) NOT NULL,
  skill_id integer,
  skill character varying(100) NOT NULL,
  question text NOT NULL,
  options jsonb DEFAULT '[]'::jsonb,
  sequence_no integer NOT NULL,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
  diagnostic_round_id uuid NOT NULL,
  CONSTRAINT assessment_questions_assessment_type_check CHECK (assessment_type::text = ANY (ARRAY['PRE'::character varying::text, 'POST'::character varying::text])),
  CONSTRAINT assessment_questions_pkey PRIMARY KEY (question_id),
  CONSTRAINT assessment_sequence_unique UNIQUE (diagnostic_round_id, assessment_type, sequence_no),
  CONSTRAINT uq_assessment_question_scope UNIQUE (question_id, project_id, assessment_type)
);

-- 설문 응답 (팀원 DB 행 수 25)
CREATE TABLE IF NOT EXISTS public.assessment_responses (
  response_id uuid DEFAULT gen_random_uuid() NOT NULL,
  project_id uuid NOT NULL,
  question_id uuid NOT NULL,
  assessment_type character varying(20) NOT NULL,
  selected_option text NOT NULL,
  score integer NOT NULL,
  answered_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
  CONSTRAINT assessment_responses_assessment_type_check CHECK (assessment_type::text = ANY (ARRAY['PRE'::character varying::text, 'POST'::character varying::text])),
  CONSTRAINT assessment_responses_pkey PRIMARY KEY (response_id),
  CONSTRAINT assessment_responses_score_check CHECK (score >= 1 AND score <= 5),
  CONSTRAINT uq_session_question_resp UNIQUE (project_id, question_id)
);

-- 도서 스킬 (팀원 DB 행 수 643)
CREATE TABLE IF NOT EXISTS public.book_skills (
  isbn character varying(20) NOT NULL,
  skill_id integer NOT NULL,
  CONSTRAINT book_skill_map_pkey PRIMARY KEY (isbn, skill_id)
);

-- 도서 (팀원 DB 행 수 345)
CREATE TABLE IF NOT EXISTS public.books (
  isbn character varying(20) NOT NULL,
  title character varying(200) NOT NULL,
  author character varying(100),
  publisher character varying(100),
  loan_count integer DEFAULT 0,
  kdc_code character varying(10) DEFAULT '004'::character varying,
  last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  record_source character varying(40) DEFAULT 'EXTERNAL_INGESTION'::character varying NOT NULL,
  source_url text,
  content_status text,
  source_verified_at timestamp with time zone,
  description text,
  image_url text,
  CONSTRAINT books_pkey PRIMARY KEY (isbn)
);

-- 자격증 스킬 (팀원 DB 행 수 115)
CREATE TABLE IF NOT EXISTS public.certification_skills (
  cert_id integer NOT NULL,
  skill_id integer NOT NULL,
  CONSTRAINT cert_skill_map_pkey PRIMARY KEY (cert_id, skill_id)
);

-- 자격증 (팀원 DB 행 수 66)
CREATE TABLE IF NOT EXISTS public.certifications (
  cert_id integer DEFAULT nextval('certifications_cert_id_seq'::regclass) NOT NULL,
  title character varying(100) NOT NULL,
  provider character varying(50),
  test_subjects text,
  career_outlook text,
  exam_type character varying(20),
  pass_score integer,
  last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  record_source character varying(40) DEFAULT 'EXTERNAL_INGESTION'::character varying NOT NULL,
  source_url text,
  content_status text,
  source_verified_at timestamp with time zone,
  description text,
  image_url text,
  CONSTRAINT certifications_pkey PRIMARY KEY (cert_id),
  CONSTRAINT certifications_title_key UNIQUE (title)
);

-- 강좌 스킬 (팀원 DB 행 수 997)
CREATE TABLE IF NOT EXISTS public.course_skills (
  course_id character varying(50) NOT NULL,
  skill_id integer NOT NULL,
  CONSTRAINT course_skill_map_pkey PRIMARY KEY (course_id, skill_id)
);

-- 강좌 (팀원 DB 행 수 718)
CREATE TABLE IF NOT EXISTS public.courses (
  course_id character varying(50) NOT NULL,
  title character varying(200) NOT NULL,
  category_name character varying(50),
  org_name character varying(100),
  url character varying(255),
  is_matchup boolean,
  cost numeric(10,2),
  duration_weeks integer DEFAULT 4,
  recruitment_status character varying(30) DEFAULT 'OPEN'::character varying,
  syllabus_summary text,
  last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  platform character varying(50) DEFAULT 'K-MOOC'::character varying NOT NULL,
  difficulty character varying(20),
  record_source character varying(40) DEFAULT 'EXTERNAL_INGESTION'::character varying NOT NULL,
  source_url text,
  content_status text,
  source_verified_at timestamp with time zone,
  image_url text,
  CONSTRAINT chk_courses_difficulty CHECK (difficulty::text = ANY (ARRAY['BEGINNER'::character varying::text, 'INTERMEDIATE'::character varying::text, 'ADVANCED'::character varying::text])),
  CONSTRAINT courses_pkey PRIMARY KEY (course_id)
);

-- 부서 계층 (팀원 DB 행 수 5)
CREATE TABLE IF NOT EXISTS public.departments (
  department_id bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
  institution_id character varying(64) NOT NULL,
  department_code text NOT NULL,
  name text NOT NULL,
  parent_department_id bigint,
  CONSTRAINT departments_check CHECK (parent_department_id IS DISTINCT FROM department_id),
  CONSTRAINT departments_department_id_institution_id_key UNIQUE (department_id, institution_id),
  CONSTRAINT departments_institution_id_department_code_key UNIQUE (institution_id, department_code),
  CONSTRAINT departments_pkey PRIMARY KEY (department_id)
);

-- 진단 회차 (팀원 DB 행 수 2)
CREATE TABLE IF NOT EXISTS public.diagnostic_rounds (
  diagnostic_round_id uuid DEFAULT gen_random_uuid() NOT NULL,
  project_id uuid NOT NULL,
  round_number integer NOT NULL,
  project_snapshot jsonb NOT NULL,
  agent_input jsonb,
  diagnostic_result jsonb,
  pre_completed_at timestamp with time zone,
  post_completed_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT diagnostic_rounds_diagnostic_round_id_project_id_key UNIQUE (diagnostic_round_id, project_id),
  CONSTRAINT diagnostic_rounds_pkey PRIMARY KEY (diagnostic_round_id),
  CONSTRAINT diagnostic_rounds_project_id_round_number_key UNIQUE (project_id, round_number),
  CONSTRAINT diagnostic_rounds_round_number_check CHECK (round_number > 0)
);

-- 보유 자격증 (팀원 DB 행 수 0)
CREATE TABLE IF NOT EXISTS public.employee_certifications (
  employee_id integer NOT NULL,
  certification_id integer NOT NULL,
  CONSTRAINT employee_certifications_pkey PRIMARY KEY (employee_id, certification_id)
);

-- 학력 (팀원 DB 행 수 0)
CREATE TABLE IF NOT EXISTS public.employee_education_records (
  education_record_id uuid DEFAULT gen_random_uuid() NOT NULL,
  employee_id integer NOT NULL,
  school_name text NOT NULL,
  education_level text NOT NULL,
  department_name text,
  major_id integer,
  CONSTRAINT employee_education_records_education_level_check CHECK (education_level = ANY (ARRAY['middle_school_or_lower'::text, 'high_school'::text, 'associate'::text, 'bachelor'::text, 'master'::text, 'doctorate'::text, 'other'::text])),
  CONSTRAINT employee_education_records_pkey PRIMARY KEY (education_record_id),
  CONSTRAINT employee_education_records_school_name_check CHECK (length(TRIM(BOTH FROM school_name)) > 0)
);

-- 직원 추천 질문 (팀원 DB 행 수 0)
CREATE TABLE IF NOT EXISTS public.employee_recommended_prompts (
  prompt_id uuid DEFAULT gen_random_uuid() NOT NULL,
  employee_id integer,
  prompt_text text,
  display_order smallint,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT employee_recommended_prompts_display_order_check CHECK (display_order >= 1 AND display_order <= 3),
  CONSTRAINT employee_recommended_prompts_employee_order_key UNIQUE (employee_id, display_order),
  CONSTRAINT employee_recommended_prompts_pkey PRIMARY KEY (prompt_id),
  CONSTRAINT employee_recommended_prompts_prompt_text_check CHECK (prompt_text IS NULL OR length(btrim(prompt_text)) > 0)
);

-- 보유 스킬 (팀원 DB 행 수 0)
CREATE TABLE IF NOT EXISTS public.employee_skills (
  employee_id integer NOT NULL,
  skill_id integer NOT NULL,
  CONSTRAINT employee_skills_pkey PRIMARY KEY (employee_id, skill_id)
);

-- 직원·로그인 계정 (팀원 DB 행 수 14)
CREATE TABLE IF NOT EXISTS public.employees (
  employee_id integer DEFAULT nextval('users_user_id_seq'::regclass) NOT NULL,
  name character varying(50) NOT NULL,
  job_id integer,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  is_degree_seeker boolean DEFAULT false,
  email character varying(255),
  department character varying(100),
  job_title character varying(100),
  grade character varying(50),
  source_type character varying(20) DEFAULT 'REAL_USER'::character varying,
  updated_at timestamp with time zone DEFAULT now(),
  institution_id character varying(64),
  employee_number text,
  password_hash text,
  department_id bigint,
  job_grade_id bigint,
  is_department_head boolean DEFAULT false NOT NULL,
  CONSTRAINT employees_department_requires_institution CHECK (department_id IS NULL OR institution_id IS NOT NULL),
  CONSTRAINT employees_grade_requires_institution CHECK (job_grade_id IS NULL OR institution_id IS NOT NULL),
  CONSTRAINT employees_head_department_required CHECK (NOT is_department_head OR department_id IS NOT NULL),
  CONSTRAINT employees_number_unique UNIQUE (institution_id, employee_number),
  CONSTRAINT employees_password_is_hash CHECK (password_hash IS NULL OR password_hash ~~ '$argon2id$%%'::text),
  CONSTRAINT users_pkey PRIMARY KEY (employee_id)
);

-- 성장 보고서 (팀원 DB 행 수 1)
CREATE TABLE IF NOT EXISTS public.growth_reports (
  report_id uuid DEFAULT gen_random_uuid() NOT NULL,
  project_id uuid NOT NULL,
  report_type character varying(30) DEFAULT 'PRE_POST'::character varying NOT NULL,
  report_content jsonb NOT NULL,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
  roadmap_id uuid NOT NULL,
  CONSTRAINT assessment_reports_pkey PRIMARY KEY (report_id),
  CONSTRAINT growth_roadmap_unique UNIQUE (roadmap_id),
  CONSTRAINT uq_session_assessment_report UNIQUE (project_id)
);

-- 기관 (팀원 DB 행 수 1)
CREATE TABLE IF NOT EXISTS public.institutions (
  institution_id character varying(64) NOT NULL,
  name character varying(255) NOT NULL,
  external_code character varying(255),
  institution_code text GENERATED ALWAYS AS (COALESCE(external_code, institution_id)) STORED,
  CONSTRAINT institution_pkey PRIMARY KEY (institution_id),
  CONSTRAINT institutions_code_unique UNIQUE (institution_code)
);

-- 직급 (팀원 DB 행 수 5)
CREATE TABLE IF NOT EXISTS public.job_grades (
  job_grade_id bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
  institution_id character varying(64) NOT NULL,
  name text NOT NULL,
  sort_order integer DEFAULT 0 NOT NULL,
  CONSTRAINT job_grades_institution_id_name_key UNIQUE (institution_id, name),
  CONSTRAINT job_grades_job_grade_id_institution_id_key UNIQUE (job_grade_id, institution_id),
  CONSTRAINT job_grades_pkey PRIMARY KEY (job_grade_id)
);

-- 직무 스킬 (팀원 DB 행 수 31)
CREATE TABLE IF NOT EXISTS public.job_skills (
  job_id integer NOT NULL,
  skill_id integer NOT NULL,
  CONSTRAINT job_skill_map_pkey PRIMARY KEY (job_id, skill_id)
);

-- 직무 (팀원 DB 행 수 80)
CREATE TABLE IF NOT EXISTS public.jobs (
  job_id integer NOT NULL,
  title character varying(100) NOT NULL,
  ncs_units text,
  last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  record_source character varying(40) DEFAULT 'EXTERNAL_INGESTION'::character varying NOT NULL,
  source_url text,
  content_status text,
  source_verified_at timestamp with time zone,
  description text,
  CONSTRAINT jobs_pkey PRIMARY KEY (job_id)
);

-- 학습 자료·스킬 벡터 (팀원 DB 행 수 1377)
CREATE TABLE IF NOT EXISTS public.learning_resource_embeddings (
  resource_type text NOT NULL,
  resource_id text NOT NULL,
  embedding_model text NOT NULL,
  dimensions integer NOT NULL,
  input_version text NOT NULL,
  input_sha256 text NOT NULL,
  embedding vector(1536) NOT NULL,
  updated_at timestamp with time zone DEFAULT now() NOT NULL,
  skill_id integer,
  course_id character varying(255),
  isbn character varying(20),
  certification_id integer,
  job_id integer,
  major_id integer,
  CONSTRAINT learning_resource_embedding_dimensions_check CHECK (dimensions = 1536),
  CONSTRAINT learning_resource_embedding_embedding_check CHECK (vector_norm(embedding) > 0::double precision),
  CONSTRAINT learning_resource_embedding_input_sha256_check CHECK (length(input_sha256) = 64),
  CONSTRAINT learning_resource_embedding_pkey PRIMARY KEY (resource_type, resource_id, embedding_model),
  CONSTRAINT resource_kind_check CHECK (resource_type = ANY (ARRAY['skills'::text, 'courses'::text, 'books'::text, 'certifications'::text, 'jobs'::text, 'majors'::text])),
  CONSTRAINT vector_one_source CHECK (num_nonnulls(skill_id, course_id, isbn, certification_id, job_id, major_id) = 1),
  CONSTRAINT vector_source_matches_key CHECK (resource_type = 'skills'::text AND skill_id::text = resource_id OR resource_type = 'courses'::text AND course_id::text = resource_id OR resource_type = 'books'::text AND isbn::text = resource_id OR resource_type = 'certifications'::text AND certification_id::text = resource_id OR resource_type = 'jobs'::text AND job_id::text = resource_id OR resource_type = 'majors'::text AND major_id::text = resource_id),
  CONSTRAINT vector_type_matches_source CHECK (
CASE resource_type
    WHEN 'skills'::text THEN skill_id IS NOT NULL
    WHEN 'courses'::text THEN course_id IS NOT NULL
    WHEN 'books'::text THEN isbn IS NOT NULL
    WHEN 'certifications'::text THEN certification_id IS NOT NULL
    WHEN 'jobs'::text THEN job_id IS NOT NULL
    WHEN 'majors'::text THEN major_id IS NOT NULL
    ELSE false
END)
);

-- 전공 스킬 (팀원 DB 행 수 202)
CREATE TABLE IF NOT EXISTS public.major_skills (
  major_id integer NOT NULL,
  skill_id integer NOT NULL,
  CONSTRAINT major_skill_map_pkey PRIMARY KEY (major_id, skill_id)
);

-- 전공 (팀원 DB 행 수 132)
CREATE TABLE IF NOT EXISTS public.majors (
  major_id integer NOT NULL,
  title character varying(100) NOT NULL,
  curriculum text,
  last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  source_url text,
  content_status text,
  source_verified_at timestamp with time zone,
  description text,
  CONSTRAINT majors_pkey PRIMARY KEY (major_id)
);

-- 프로젝트·계획 (팀원 DB 행 수 2)
CREATE TABLE IF NOT EXISTS public.projects (
  project_id uuid DEFAULT gen_random_uuid() NOT NULL,
  employee_id integer NOT NULL,
  project_name character varying(255) NOT NULL,
  status character varying(50) DEFAULT 'DRAFT'::character varying NOT NULL,
  current_stage integer DEFAULT 1 NOT NULL,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
  updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
  extracted_text text,
  draft_plan text,
  refined_plan text,
  project_goal text,
  project_scope text,
  tech_stack jsonb DEFAULT '[]'::jsonb NOT NULL,
  milestones jsonb DEFAULT '[]'::jsonb NOT NULL,
  key_issues jsonb DEFAULT '[]'::jsonb NOT NULL,
  deliverables jsonb DEFAULT '[]'::jsonb NOT NULL,
  validation_criteria jsonb DEFAULT '[]'::jsonb NOT NULL,
  draft_conversations jsonb DEFAULT '[]'::jsonb NOT NULL,
  draft_choices jsonb DEFAULT '[]'::jsonb NOT NULL,
  CONSTRAINT roadmap_sessions_pkey PRIMARY KEY (project_id)
);

-- 운영 프롬프트 (팀원 DB 행 수 4)
CREATE TABLE IF NOT EXISTS public.prompt_versions (
  prompt_version_id uuid DEFAULT gen_random_uuid() NOT NULL,
  agent_id character varying(50) NOT NULL,
  version_num integer NOT NULL,
  system_prompt text NOT NULL,
  is_active boolean DEFAULT false NOT NULL,
  parent_version_id uuid,
  change_reason text NOT NULL,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
  deactivated_at timestamp with time zone,
  CONSTRAINT prompt_versions_agent_id_check CHECK (agent_id::text = ANY (ARRAY['agent_practical'::character varying::text, 'agent_certified'::character varying::text, 'agent_fasttrack'::character varying::text])),
  CONSTRAINT prompt_versions_pkey PRIMARY KEY (prompt_version_id),
  CONSTRAINT uq_agent_version UNIQUE (agent_id, version_num)
);

-- 부서장 코멘트 (팀원 DB 행 수 0)
CREATE TABLE IF NOT EXISTS public.roadmap_comments (
  comment_id uuid DEFAULT gen_random_uuid() NOT NULL,
  roadmap_id uuid NOT NULL,
  author_employee_id integer NOT NULL,
  body text NOT NULL,
  created_at timestamp with time zone DEFAULT now() NOT NULL,
  updated_at timestamp with time zone DEFAULT now() NOT NULL,
  modification_completed_at timestamp with time zone,
  CONSTRAINT roadmap_comments_body_check CHECK (length(TRIM(BOTH FROM body)) > 0),
  CONSTRAINT roadmap_comments_pkey PRIMARY KEY (comment_id)
);

-- 단계별 학습 자료 (팀원 DB 행 수 9)
CREATE TABLE IF NOT EXISTS public.roadmap_step_resources (
  step_resource_id bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
  step_id uuid NOT NULL,
  course_id character varying(255),
  isbn character varying(20),
  certification_id integer,
  CONSTRAINT roadmap_step_resources_check CHECK (num_nonnulls(course_id, isbn, certification_id) = 1),
  CONSTRAINT roadmap_step_resources_pkey PRIMARY KEY (step_resource_id),
  CONSTRAINT roadmap_step_resources_step_id_certification_id_key UNIQUE (step_id, certification_id),
  CONSTRAINT roadmap_step_resources_step_id_course_id_key UNIQUE (step_id, course_id),
  CONSTRAINT roadmap_step_resources_step_id_isbn_key UNIQUE (step_id, isbn)
);

-- 로드맵 단계 (팀원 DB 행 수 3)
CREATE TABLE IF NOT EXISTS public.roadmap_steps (
  step_id uuid DEFAULT gen_random_uuid() NOT NULL,
  roadmap_id uuid NOT NULL,
  step_order integer NOT NULL,
  title text NOT NULL,
  activity text,
  estimated_duration text,
  target_start_date date,
  target_end_date date,
  estimated_cost numeric(14,2),
  is_completed boolean DEFAULT false NOT NULL,
  completed_at timestamp with time zone,
  details jsonb DEFAULT '{}'::jsonb NOT NULL,
  CONSTRAINT roadmap_steps_check CHECK (target_end_date IS NULL OR target_start_date IS NULL OR target_end_date >= target_start_date),
  CONSTRAINT roadmap_steps_check1 CHECK (is_completed = (completed_at IS NOT NULL)),
  CONSTRAINT roadmap_steps_estimated_cost_check CHECK (estimated_cost >= 0::numeric),
  CONSTRAINT roadmap_steps_pkey PRIMARY KEY (step_id),
  CONSTRAINT roadmap_steps_roadmap_id_step_order_key UNIQUE (roadmap_id, step_order),
  CONSTRAINT roadmap_steps_step_order_check CHECK (step_order > 0)
);

-- 선택 로드맵 (팀원 DB 행 수 1)
CREATE TABLE IF NOT EXISTS public.roadmaps (
  roadmap_id uuid DEFAULT gen_random_uuid() NOT NULL,
  project_id uuid NOT NULL,
  strategy_type character varying(50) NOT NULL,
  strategy_title character varying(255),
  summary text,
  content jsonb NOT NULL,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
  selected_at timestamp with time zone,
  report_content jsonb,
  baseline_content jsonb NOT NULL,
  updated_at timestamp with time zone DEFAULT now() NOT NULL,
  diagnostic_round_id uuid NOT NULL,
  CONSTRAINT roadmap_diagnostic_unique UNIQUE (diagnostic_round_id),
  CONSTRAINT roadmap_generations_pkey PRIMARY KEY (roadmap_id),
  CONSTRAINT roadmap_project_identity UNIQUE (roadmap_id, project_id),
  CONSTRAINT uq_generation_scope UNIQUE (roadmap_id, project_id)
);

-- 스킬 태그 (팀원 DB 행 수 36)
CREATE TABLE IF NOT EXISTS public.skill_tags (
  skill_id integer DEFAULT nextval('skill_tags_skill_id_seq'::regclass) NOT NULL,
  name character varying(50) NOT NULL,
  category character varying(50) DEFAULT 'IT/Tech'::character varying,
  CONSTRAINT skill_tags_pkey PRIMARY KEY (skill_id),
  CONSTRAINT skill_tags_skill_name_key UNIQUE (name)
);

-- 평가기준 항목 (팀원 DB 행 수 70)
CREATE TABLE IF NOT EXISTS regulations.evaluation_item_definitions (
  evaluation_item_definition_id character varying(64) NOT NULL,
  evaluation_result_schema_id character varying(64) NOT NULL,
  parent_item_id character varying(64),
  skill_id integer,
  item_code character varying(255) NOT NULL,
  item_name character varying(255) NOT NULL,
  value_kind character varying(40) NOT NULL,
  aggregation_role character varying(40) NOT NULL,
  score_min numeric(12,3),
  score_max numeric(12,3),
  weight_percent numeric(6,3),
  unit character varying(40),
  scale_note text,
  display_order integer NOT NULL,
  definition_note text,
  CONSTRAINT evaluation_item_definition_id_schema_uq UNIQUE (evaluation_item_definition_id, evaluation_result_schema_id),
  CONSTRAINT evaluation_item_definition_pkey PRIMARY KEY (evaluation_item_definition_id),
  CONSTRAINT evaluation_item_definition_schema_code_uq UNIQUE (evaluation_result_schema_id, item_code)
);

-- 평가기준 체계 (팀원 DB 행 수 11)
CREATE TABLE IF NOT EXISTS regulations.evaluation_result_schemas (
  evaluation_result_schema_id character varying(64) NOT NULL,
  institution_id character varying(64) NOT NULL,
  schema_name character varying(255) NOT NULL,
  version_label character varying(255) NOT NULL,
  evaluation_kind character varying(40) NOT NULL,
  applicability_condition jsonb NOT NULL,
  applicability_note text,
  effective_from date,
  effective_to date,
  rule_origin character varying(40) NOT NULL,
  source_status character varying(40) NOT NULL,
  review_status character varying(40) NOT NULL,
  calculation_rule jsonb,
  calculation_status character varying(40) NOT NULL,
  source_note text,
  CONSTRAINT evaluation_result_schema_pkey PRIMARY KEY (evaluation_result_schema_id)
);

-- 평가기준 출처 (팀원 DB 행 수 172)
CREATE TABLE IF NOT EXISTS regulations.evaluation_schema_sources (
  evaluation_schema_source_id character varying(64) NOT NULL,
  evaluation_result_schema_id character varying(64) NOT NULL,
  evaluation_item_definition_id character varying(64),
  regulation_node_id character varying(64) NOT NULL,
  source_role character varying(40) NOT NULL,
  review_status character varying(40) NOT NULL,
  source_note text,
  CONSTRAINT evaluation_schema_source_pkey PRIMARY KEY (evaluation_schema_source_id)
);

-- 규정 청크 벡터 (팀원 DB 행 수 1410)
CREATE TABLE IF NOT EXISTS regulations.rag_chunk_embeddings (
  rag_chunk_id character varying(64) NOT NULL,
  embedding_model text NOT NULL,
  dimensions integer NOT NULL,
  input_version text NOT NULL,
  input_sha256 text NOT NULL,
  embedding vector(1536) NOT NULL,
  created_at timestamp with time zone DEFAULT now() NOT NULL,
  updated_at timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT rag_chunk_embedding_dimensions_check CHECK (dimensions = 1536),
  CONSTRAINT rag_chunk_embedding_embedding_check CHECK (vector_norm(embedding) > 0::double precision),
  CONSTRAINT rag_chunk_embedding_input_sha256_check CHECK (length(input_sha256) = 64),
  CONSTRAINT rag_chunk_embedding_pkey PRIMARY KEY (rag_chunk_id, embedding_model)
);

-- 청크 원문 출처 (팀원 DB 행 수 1774)
CREATE TABLE IF NOT EXISTS regulations.rag_chunk_sources (
  rag_chunk_source_id character varying(64) NOT NULL,
  rag_chunk_id character varying(64) NOT NULL,
  regulation_node_id character varying(64) NOT NULL,
  source_order integer NOT NULL,
  source_role character varying(40) NOT NULL,
  source_span jsonb,
  CONSTRAINT rag_chunk_source_pkey PRIMARY KEY (rag_chunk_source_id),
  CONSTRAINT rag_chunk_source_rag_chunk_id_source_order_key UNIQUE (rag_chunk_id, source_order)
);

-- 규정 검색 청크 (팀원 DB 행 수 1552)
CREATE TABLE IF NOT EXISTS regulations.rag_chunks (
  rag_chunk_id character varying(64) NOT NULL,
  regulation_version_id character varying(64) NOT NULL,
  chunk_text text NOT NULL,
  chunk_type character varying(40) NOT NULL,
  context_path character varying(1024) NOT NULL,
  content_hash character varying(128) NOT NULL,
  chunking_version character varying(255) NOT NULL,
  index_revision character varying(255) NOT NULL,
  embedding_model character varying(255),
  search_status character varying(40) NOT NULL,
  created_at timestamp with time zone NOT NULL,
  token_count integer,
  CONSTRAINT rag_chunk_pkey PRIMARY KEY (rag_chunk_id)
);

-- 규정 출처 파일 (팀원 DB 행 수 28)
CREATE TABLE IF NOT EXISTS regulations.regulation_files (
  regulation_file_id character varying(64) NOT NULL,
  regulation_version_id character varying(64) NOT NULL,
  source_file_id character varying(64),
  file_name character varying(255) NOT NULL,
  file_format character varying(40) NOT NULL,
  file_role character varying(40) NOT NULL,
  storage_key character varying(2048) NOT NULL,
  source_type character varying(40) NOT NULL,
  source_url character varying(2048),
  retrieved_at timestamp with time zone NOT NULL,
  file_hash character varying(128) NOT NULL,
  is_extraction_source boolean NOT NULL,
  parse_status character varying(40) NOT NULL,
  access_level character varying(40) NOT NULL,
  CONSTRAINT regulation_file_pkey PRIMARY KEY (regulation_file_id)
);

-- 규정 원문 구조 (팀원 DB 행 수 3451)
CREATE TABLE IF NOT EXISTS regulations.regulation_nodes (
  regulation_node_id character varying(64) NOT NULL,
  regulation_version_id character varying(64) NOT NULL,
  regulation_file_id character varying(64) NOT NULL,
  parent_node_id character varying(64),
  node_type character varying(40) NOT NULL,
  label character varying(255) NOT NULL,
  title character varying(255),
  path character varying(1024) NOT NULL,
  display_order integer NOT NULL,
  body_text text NOT NULL,
  source_locator jsonb NOT NULL,
  effective_from_override date,
  effective_to_override date,
  extraction_status character varying(40) NOT NULL,
  review_note text,
  CONSTRAINT regulation_node_pkey PRIMARY KEY (regulation_node_id)
);

-- 규정 참조 (팀원 DB 행 수 462)
CREATE TABLE IF NOT EXISTS regulations.regulation_references (
  regulation_reference_id character varying(64) NOT NULL,
  regulation_node_id character varying(64) NOT NULL,
  reference_type character varying(40) NOT NULL,
  target_text text NOT NULL,
  target_regulation_id character varying(64),
  target_version_id character varying(64),
  target_node_id character varying(64),
  resolution_status character varying(40) NOT NULL,
  review_note text,
  CONSTRAINT regulation_reference_pkey PRIMARY KEY (regulation_reference_id)
);

-- 규정 적용 범위 (팀원 DB 행 수 389)
CREATE TABLE IF NOT EXISTS regulations.regulation_scopes (
  regulation_scope_id character varying(64) NOT NULL,
  regulation_node_id character varying(64) NOT NULL,
  scope_type character varying(40) NOT NULL,
  condition_text text NOT NULL,
  condition_json jsonb,
  applies_to_node_id character varying(64),
  review_status character varying(40) NOT NULL,
  CONSTRAINT regulation_scope_pkey PRIMARY KEY (regulation_scope_id)
);

-- 규정 버전 (팀원 DB 행 수 28)
CREATE TABLE IF NOT EXISTS regulations.regulation_versions (
  regulation_version_id character varying(64) NOT NULL,
  regulation_id character varying(64) NOT NULL,
  version_label character varying(255) NOT NULL,
  title_at_version character varying(255) NOT NULL,
  content_kind character varying(40) NOT NULL,
  coverage_status character varying(40) NOT NULL,
  amendment_date date,
  effective_from date,
  effective_to date,
  date_status character varying(40) NOT NULL,
  review_status character varying(40) NOT NULL,
  availability_status character varying(40) NOT NULL,
  previous_version_id character varying(64),
  review_note text,
  CONSTRAINT regulation_version_pkey PRIMARY KEY (regulation_version_id)
);

-- 규정 (팀원 DB 행 수 28)
CREATE TABLE IF NOT EXISTS regulations.regulations (
  regulation_id character varying(64) NOT NULL,
  institution_id character varying(64) NOT NULL,
  name character varying(255) NOT NULL,
  category character varying(40) NOT NULL,
  document_kind character varying(40) NOT NULL,
  CONSTRAINT regulation_pkey PRIMARY KEY (regulation_id)
);

-- 외래키
ALTER TABLE public.assessment_questions ADD CONSTRAINT assessment_question_round_scope FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES public.diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE;
ALTER TABLE public.assessment_questions ADD CONSTRAINT assessment_questions_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;
ALTER TABLE public.assessment_questions ADD CONSTRAINT assessment_questions_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id);
ALTER TABLE public.assessment_responses ADD CONSTRAINT assessment_responses_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;
ALTER TABLE public.assessment_responses ADD CONSTRAINT fk_response_question_scope FOREIGN KEY (question_id, project_id, assessment_type) REFERENCES public.assessment_questions(question_id, project_id, assessment_type) ON DELETE CASCADE;
ALTER TABLE public.book_skills ADD CONSTRAINT book_skill_map_isbn_fkey FOREIGN KEY (isbn) REFERENCES public.books(isbn) ON DELETE CASCADE;
ALTER TABLE public.book_skills ADD CONSTRAINT book_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;
ALTER TABLE public.certification_skills ADD CONSTRAINT cert_skill_map_cert_id_fkey FOREIGN KEY (cert_id) REFERENCES public.certifications(cert_id) ON DELETE CASCADE;
ALTER TABLE public.certification_skills ADD CONSTRAINT cert_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;
ALTER TABLE public.course_skills ADD CONSTRAINT course_skill_map_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(course_id) ON DELETE CASCADE;
ALTER TABLE public.course_skills ADD CONSTRAINT course_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;
ALTER TABLE public.departments ADD CONSTRAINT departments_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);
ALTER TABLE public.departments ADD CONSTRAINT departments_parent_department_id_institution_id_fkey FOREIGN KEY (parent_department_id, institution_id) REFERENCES public.departments(department_id, institution_id);
ALTER TABLE public.diagnostic_rounds ADD CONSTRAINT diagnostic_rounds_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;
ALTER TABLE public.employee_certifications ADD CONSTRAINT employee_certifications_certification_id_fkey FOREIGN KEY (certification_id) REFERENCES public.certifications(cert_id);
ALTER TABLE public.employee_certifications ADD CONSTRAINT employee_certifications_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;
ALTER TABLE public.employee_education_records ADD CONSTRAINT employee_education_records_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;
ALTER TABLE public.employee_education_records ADD CONSTRAINT employee_education_records_major_id_fkey FOREIGN KEY (major_id) REFERENCES public.majors(major_id);
ALTER TABLE public.employee_recommended_prompts ADD CONSTRAINT employee_recommended_prompts_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;
ALTER TABLE public.employee_skills ADD CONSTRAINT employee_skills_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;
ALTER TABLE public.employee_skills ADD CONSTRAINT employee_skills_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id);
ALTER TABLE public.employees ADD CONSTRAINT employees_department_scope FOREIGN KEY (department_id, institution_id) REFERENCES public.departments(department_id, institution_id);
ALTER TABLE public.employees ADD CONSTRAINT employees_grade_scope FOREIGN KEY (job_grade_id, institution_id) REFERENCES public.job_grades(job_grade_id, institution_id);
ALTER TABLE public.employees ADD CONSTRAINT employees_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);
ALTER TABLE public.employees ADD CONSTRAINT users_target_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE SET NULL;
ALTER TABLE public.growth_reports ADD CONSTRAINT assessment_reports_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;
ALTER TABLE public.growth_reports ADD CONSTRAINT growth_roadmap_fk FOREIGN KEY (roadmap_id) REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE;
ALTER TABLE public.growth_reports ADD CONSTRAINT growth_same_project_fk FOREIGN KEY (roadmap_id, project_id) REFERENCES public.roadmaps(roadmap_id, project_id) ON DELETE CASCADE;
ALTER TABLE public.job_grades ADD CONSTRAINT job_grades_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);
ALTER TABLE public.job_skills ADD CONSTRAINT job_skill_map_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE CASCADE;
ALTER TABLE public.job_skills ADD CONSTRAINT job_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;
ALTER TABLE public.learning_resource_embeddings ADD CONSTRAINT learning_resource_embeddings_certification_id_fkey FOREIGN KEY (certification_id) REFERENCES public.certifications(cert_id) ON DELETE CASCADE;
ALTER TABLE public.learning_resource_embeddings ADD CONSTRAINT learning_resource_embeddings_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(course_id) ON DELETE CASCADE;
ALTER TABLE public.learning_resource_embeddings ADD CONSTRAINT learning_resource_embeddings_isbn_fkey FOREIGN KEY (isbn) REFERENCES public.books(isbn) ON DELETE CASCADE;
ALTER TABLE public.learning_resource_embeddings ADD CONSTRAINT learning_resource_embeddings_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE CASCADE;
ALTER TABLE public.learning_resource_embeddings ADD CONSTRAINT learning_resource_embeddings_major_id_fkey FOREIGN KEY (major_id) REFERENCES public.majors(major_id) ON DELETE CASCADE;
ALTER TABLE public.learning_resource_embeddings ADD CONSTRAINT learning_resource_embeddings_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;
ALTER TABLE public.major_skills ADD CONSTRAINT major_skill_map_major_id_fkey FOREIGN KEY (major_id) REFERENCES public.majors(major_id) ON DELETE CASCADE;
ALTER TABLE public.major_skills ADD CONSTRAINT major_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;
ALTER TABLE public.projects ADD CONSTRAINT roadmap_sessions_user_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;
ALTER TABLE public.prompt_versions ADD CONSTRAINT prompt_versions_parent_version_id_fkey FOREIGN KEY (parent_version_id) REFERENCES public.prompt_versions(prompt_version_id);
ALTER TABLE public.roadmap_comments ADD CONSTRAINT roadmap_comments_author_employee_id_fkey FOREIGN KEY (author_employee_id) REFERENCES public.employees(employee_id);
ALTER TABLE public.roadmap_comments ADD CONSTRAINT roadmap_comments_roadmap_id_fkey FOREIGN KEY (roadmap_id) REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE;
ALTER TABLE public.roadmap_step_resources ADD CONSTRAINT roadmap_step_resources_certification_id_fkey FOREIGN KEY (certification_id) REFERENCES public.certifications(cert_id);
ALTER TABLE public.roadmap_step_resources ADD CONSTRAINT roadmap_step_resources_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(course_id);
ALTER TABLE public.roadmap_step_resources ADD CONSTRAINT roadmap_step_resources_isbn_fkey FOREIGN KEY (isbn) REFERENCES public.books(isbn);
ALTER TABLE public.roadmap_step_resources ADD CONSTRAINT roadmap_step_resources_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.roadmap_steps(step_id) ON DELETE CASCADE;
ALTER TABLE public.roadmap_steps ADD CONSTRAINT roadmap_steps_roadmap_id_fkey FOREIGN KEY (roadmap_id) REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE;
ALTER TABLE public.roadmaps ADD CONSTRAINT roadmap_generations_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;
ALTER TABLE public.roadmaps ADD CONSTRAINT roadmap_round_scope FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES public.diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE;
ALTER TABLE regulations.evaluation_item_definitions ADD CONSTRAINT evaluation_item_definition_parent_fk FOREIGN KEY (parent_item_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id);
ALTER TABLE regulations.evaluation_item_definitions ADD CONSTRAINT evaluation_item_definition_schema_fk FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id);
ALTER TABLE regulations.evaluation_item_definitions ADD CONSTRAINT evaluation_item_definition_skill_fk FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id);
ALTER TABLE regulations.evaluation_result_schemas ADD CONSTRAINT evaluation_result_schema_institution_fk FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);
ALTER TABLE regulations.evaluation_schema_sources ADD CONSTRAINT evaluation_schema_source_id_schema_fk FOREIGN KEY (evaluation_item_definition_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id);
ALTER TABLE regulations.evaluation_schema_sources ADD CONSTRAINT evaluation_schema_source_node_fk FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.evaluation_schema_sources ADD CONSTRAINT evaluation_schema_source_schema_fk FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id);
ALTER TABLE regulations.rag_chunk_embeddings ADD CONSTRAINT rag_chunk_embedding_rag_chunk_id_fkey FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id) ON DELETE CASCADE;
ALTER TABLE regulations.rag_chunk_sources ADD CONSTRAINT rag_chunk_source_rag_chunk_id_fkey FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id);
ALTER TABLE regulations.rag_chunk_sources ADD CONSTRAINT rag_chunk_source_regulation_node_id_fkey FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.rag_chunks ADD CONSTRAINT rag_chunk_regulation_version_id_fkey FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);
ALTER TABLE regulations.regulation_files ADD CONSTRAINT regulation_file_regulation_version_id_fkey FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);
ALTER TABLE regulations.regulation_files ADD CONSTRAINT regulation_file_source_file_id_fkey FOREIGN KEY (source_file_id) REFERENCES regulations.regulation_files(regulation_file_id);
ALTER TABLE regulations.regulation_nodes ADD CONSTRAINT regulation_node_parent_node_id_fkey FOREIGN KEY (parent_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.regulation_nodes ADD CONSTRAINT regulation_node_regulation_file_id_fkey FOREIGN KEY (regulation_file_id) REFERENCES regulations.regulation_files(regulation_file_id);
ALTER TABLE regulations.regulation_nodes ADD CONSTRAINT regulation_node_regulation_version_id_fkey FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);
ALTER TABLE regulations.regulation_references ADD CONSTRAINT regulation_reference_regulation_node_id_fkey FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.regulation_references ADD CONSTRAINT regulation_reference_target_node_id_fkey FOREIGN KEY (target_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.regulation_references ADD CONSTRAINT regulation_reference_target_regulation_id_fkey FOREIGN KEY (target_regulation_id) REFERENCES regulations.regulations(regulation_id);
ALTER TABLE regulations.regulation_references ADD CONSTRAINT regulation_reference_target_version_id_fkey FOREIGN KEY (target_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);
ALTER TABLE regulations.regulation_scopes ADD CONSTRAINT regulation_scope_applies_to_node_id_fkey FOREIGN KEY (applies_to_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.regulation_scopes ADD CONSTRAINT regulation_scope_regulation_node_id_fkey FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);
ALTER TABLE regulations.regulation_versions ADD CONSTRAINT regulation_version_previous_version_id_fkey FOREIGN KEY (previous_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);
ALTER TABLE regulations.regulation_versions ADD CONSTRAINT regulation_version_regulation_id_fkey FOREIGN KEY (regulation_id) REFERENCES regulations.regulations(regulation_id);
ALTER TABLE regulations.regulations ADD CONSTRAINT regulation_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);
ALTER SEQUENCE public.certifications_cert_id_seq OWNED BY public.certifications.cert_id;
ALTER SEQUENCE public.users_user_id_seq OWNED BY public.employees.employee_id;
ALTER SEQUENCE public.skill_tags_skill_id_seq OWNED BY public.skill_tags.skill_id;
