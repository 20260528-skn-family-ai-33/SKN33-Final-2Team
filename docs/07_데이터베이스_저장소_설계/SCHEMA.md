# DB 테이블과 관계

2026-10-27 최종 ERD·스키마·외부 백업 manifest 기준. 전체 53테이블(운영45·관리2·보관6), 22,284행·87개 FK다. [구현·검증](README.md)과 함께 확인한다.

## `growpath_legacy.agent_generations` · 71행

기본키: generation_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `generation_id` | uuid | 아니오 |
| `request_id` | uuid | 아니오 |
| `agent_id` | character varying(50) | 아니오 |
| `prompt_version_id` | uuid | 예 |
| `provider` | character varying(50) | 아니오 |
| `model` | character varying(100) | 아니오 |
| `roadmap_content` | jsonb | 아니오 |
| `summary` | text | 아니오 |
| `latency_ms` | integer | 아니오 |
| `status` | character varying(20) | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

- FK `prompt_version_id` → `public.prompt_versions(prompt_version_id)`

- FK `request_id` → `growpath_legacy.roadmap_requests(request_id)`

## `growpath_legacy.agent_selections` · 20행

기본키: selection_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `selection_id` | uuid | 아니오 |
| `request_id` | uuid | 아니오 |
| `chosen_generation_id` | uuid | 아니오 |
| `chosen_agent_id` | character varying(50) | 아니오 |
| `selection_reason` | text | 예 |
| `user_type` | character varying(20) | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

- FK `chosen_generation_id` → `growpath_legacy.agent_generations(generation_id)`

- FK `request_id` → `growpath_legacy.roadmap_requests(request_id)`

## `growpath_legacy.finetuning_datasets` · 2행

기본키: dataset_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `dataset_id` | uuid | 아니오 |
| `dataset_type` | character varying(20) | 아니오 |
| `record_count` | integer | 아니오 |
| `export_path` | text | 아니오 |
| `pii_masked` | boolean | 아니오 |
| `filter_criteria` | jsonb | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

## `growpath_legacy.preference_pairs` · 4행

기본키: pair_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `pair_id` | uuid | 아니오 |
| `request_id` | uuid | 아니오 |
| `chosen_generation_id` | uuid | 아니오 |
| `rejected_generation_id` | uuid | 아니오 |
| `prompt_input` | jsonb | 아니오 |
| `chosen_output` | jsonb | 아니오 |
| `rejected_output` | jsonb | 아니오 |
| `user_type` | character varying(20) | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

- FK `chosen_generation_id` → `growpath_legacy.agent_generations(generation_id)`

- FK `rejected_generation_id` → `growpath_legacy.agent_generations(generation_id)`

- FK `request_id` → `growpath_legacy.roadmap_requests(request_id)`

## `growpath_legacy.roadmap_requests` · 25행

기본키: request_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `request_id` | uuid | 아니오 |
| `user_type` | character varying(20) | 아니오 |
| `employee_id` | character varying(64) | 예 |
| `raw_user_prompt` | text | 아니오 |
| `conversation_history` | jsonb | 아니오 |
| `user_requirements` | jsonb | 아니오 |
| `retrieved_context` | jsonb | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

## `growpath_legacy.test_mock_profiles` · 39행

기본키: profile_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `profile_id` | uuid | 아니오 |
| `source_type` | character varying(20) | 아니오 |
| `profile_name` | character varying(100) | 아니오 |
| `department` | character varying(100) | 아니오 |
| `grade` | character varying(50) | 아니오 |
| `job_title` | character varying(100) | 아니오 |
| `career_years` | integer | 아니오 |
| `current_skills` | jsonb | 아니오 |
| `target_skills` | jsonb | 아니오 |
| `work_context_summary` | text | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

## `growpath_meta.catalog_api_sources` · 2433행

기본키: resource_type, source, external_key

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `resource_type` | text | 아니오 |
| `source` | text | 아니오 |
| `external_key` | text | 아니오 |
| `entity_key` | text | 아니오 |
| `payload` | jsonb | 아니오 |
| `mapping_evidence` | jsonb | 아니오 |
| `fetched_at` | timestamp with time zone | 아니오 |

## `growpath_meta.schema_migrations` · 22행

기본키: version

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `version` | text | 아니오 |
| `sha256` | text | 아니오 |
| `applied_at` | timestamp with time zone | 아니오 |

## `knowledge.chunks` · 442행

기본키: chunk_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `chunk_id` | text | 아니오 |
| `document_id` | text | 아니오 |
| `display_order` | integer | 아니오 |
| `chunk_text` | text | 아니오 |
| `chunk_text_sha256` | text | 아니오 |
| `is_virtual` | boolean | 아니오 |
| `metadata` | jsonb | 아니오 |
| `embedding_model` | text | 예 |
| `dimensions` | integer | 예 |
| `input_sha256` | text | 예 |
| `embedding` | vector(1536) | 예 |
| `embedded_at` | timestamp with time zone | 예 |
| `created_at` | timestamp with time zone | 아니오 |

- FK `document_id` → `knowledge.documents(document_id)`

## `knowledge.documents` · 4행

기본키: document_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `document_id` | text | 아니오 |
| `category` | text | 아니오 |
| `title` | text | 아니오 |
| `document_kind` | text | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |

## `public.assessment_questions` · 25행

기본키: question_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `question_id` | uuid | 아니오 |
| `project_id` | uuid | 아니오 |
| `assessment_type` | character varying(20) | 아니오 |
| `skill_id` | integer | 예 |
| `skill` | character varying(100) | 아니오 |
| `question` | text | 아니오 |
| `options` | jsonb | 예 |
| `sequence_no` | integer | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `diagnostic_round_id` | uuid | 아니오 |

- FK `diagnostic_round_id, project_id` → `public.diagnostic_rounds(diagnostic_round_id, project_id)`

- FK `project_id` → `public.projects(project_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.assessment_responses` · 25행

기본키: response_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `response_id` | uuid | 아니오 |
| `project_id` | uuid | 아니오 |
| `question_id` | uuid | 아니오 |
| `assessment_type` | character varying(20) | 아니오 |
| `selected_option` | text | 아니오 |
| `score` | integer | 아니오 |
| `answered_at` | timestamp with time zone | 아니오 |

- FK `project_id` → `public.projects(project_id)`

- FK `question_id, project_id, assessment_type` → `public.assessment_questions(question_id, project_id, assessment_type)`

## `public.book_skills` · 506행

기본키: isbn, skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `isbn` | character varying(20) | 아니오 |
| `skill_id` | integer | 아니오 |

- FK `isbn` → `public.books(isbn)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.books` · 334행

기본키: isbn

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `isbn` | character varying(20) | 아니오 |
| `title` | character varying(200) | 아니오 |
| `author` | character varying(100) | 예 |
| `publisher` | character varying(100) | 예 |
| `loan_count` | integer | 예 |
| `kdc_code` | character varying(10) | 예 |
| `last_batch_updated` | timestamp with time zone | 예 |
| `record_source` | character varying(40) | 아니오 |
| `source_url` | text | 예 |
| `content_status` | text | 예 |
| `source_verified_at` | timestamp with time zone | 예 |
| `description` | text | 예 |
| `image_url` | text | 예 |
| `ai_mention` | text | 예 |

## `public.certification_skills` · 43행

기본키: cert_id, skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `cert_id` | integer | 아니오 |
| `skill_id` | integer | 아니오 |

- FK `cert_id` → `public.certifications(cert_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.certifications` · 26행

기본키: cert_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `cert_id` | integer | 아니오 |
| `title` | character varying(100) | 아니오 |
| `provider` | character varying(50) | 예 |
| `test_subjects` | text | 예 |
| `career_outlook` | text | 예 |
| `exam_type` | character varying(20) | 예 |
| `pass_score` | integer | 예 |
| `last_batch_updated` | timestamp with time zone | 예 |
| `record_source` | character varying(40) | 아니오 |
| `source_url` | text | 예 |
| `content_status` | text | 예 |
| `source_verified_at` | timestamp with time zone | 예 |
| `description` | text | 예 |
| `image_url` | text | 예 |
| `ai_mention` | text | 예 |

## `public.course_skills` · 3658행

기본키: course_id, skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `course_id` | character varying(50) | 아니오 |
| `skill_id` | integer | 아니오 |

- FK `course_id` → `public.courses(course_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.courses` · 2060행

기본키: course_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `course_id` | character varying(50) | 아니오 |
| `title` | character varying(200) | 아니오 |
| `category_name` | character varying(50) | 예 |
| `org_name` | character varying(100) | 예 |
| `url` | character varying(255) | 예 |
| `is_matchup` | boolean | 예 |
| `cost` | numeric(10,2) | 예 |
| `duration_weeks` | integer | 예 |
| `recruitment_status` | character varying(30) | 예 |
| `syllabus_summary` | text | 예 |
| `last_batch_updated` | timestamp with time zone | 예 |
| `platform` | character varying(50) | 아니오 |
| `difficulty` | character varying(20) | 예 |
| `record_source` | character varying(40) | 아니오 |
| `source_url` | text | 예 |
| `content_status` | text | 예 |
| `source_verified_at` | timestamp with time zone | 예 |
| `image_url` | text | 예 |
| `enrollment_start` | timestamp with time zone | 예 |
| `enrollment_end` | timestamp with time zone | 예 |
| `enrollment_period_type` | text | 아니오 |
| `ai_mention` | text | 예 |

## `public.departments` · 14행

기본키: department_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `department_id` | bigint | 아니오 |
| `institution_id` | character varying(64) | 아니오 |
| `department_code` | text | 아니오 |
| `name` | text | 아니오 |
| `parent_department_id` | bigint | 예 |

- FK `institution_id` → `public.institutions(institution_id)`

- FK `parent_department_id, institution_id` → `public.departments(department_id, institution_id)`

## `public.diagnostic_rounds` · 2행

기본키: diagnostic_round_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `diagnostic_round_id` | uuid | 아니오 |
| `project_id` | uuid | 아니오 |
| `round_number` | integer | 아니오 |
| `project_snapshot` | jsonb | 아니오 |
| `agent_input` | jsonb | 예 |
| `diagnostic_result` | jsonb | 예 |
| `pre_completed_at` | timestamp with time zone | 예 |
| `post_completed_at` | timestamp with time zone | 예 |
| `created_at` | timestamp with time zone | 아니오 |

- FK `project_id` → `public.projects(project_id)`

## `public.employee_certifications` · 96행

기본키: employee_id, certification_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `employee_id` | integer | 아니오 |
| `certification_id` | integer | 아니오 |

- FK `certification_id` → `public.certifications(cert_id)`

- FK `employee_id` → `public.employees(employee_id)`

## `public.employee_education_records` · 100행

기본키: education_record_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `education_record_id` | uuid | 아니오 |
| `employee_id` | integer | 아니오 |
| `school_name` | text | 아니오 |
| `education_level` | text | 아니오 |
| `department_name` | text | 예 |
| `major_id` | integer | 예 |
| `enrollment_date` | date | 예 |
| `graduation_date` | date | 예 |

- FK `employee_id` → `public.employees(employee_id)`

- FK `major_id` → `public.majors(major_id)`

## `public.employee_input_profiles` · 0행

기본키: employee_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `employee_id` | integer | 아니오 |
| `experience_summary` | text | 예 |
| `development_years` | numeric(6,2) | 예 |
| `technology_experience` | text | 예 |
| `project_experience` | text | 예 |
| `learning_history` | text | 예 |
| `learning_preferences` | jsonb | 아니오 |
| `submission_note` | text | 예 |
| `updated_at` | timestamp with time zone | 아니오 |

- FK `employee_id` → `public.employees(employee_id)`

## `public.employee_recommended_prompts` · 0행

기본키: prompt_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `prompt_id` | uuid | 아니오 |
| `employee_id` | integer | 예 |
| `prompt_text` | text | 예 |
| `display_order` | smallint | 예 |
| `updated_at` | timestamp with time zone | 예 |

- FK `employee_id` → `public.employees(employee_id)`

## `public.employee_skills` · 293행

기본키: employee_id, skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `employee_id` | integer | 아니오 |
| `skill_id` | integer | 아니오 |

- FK `employee_id` → `public.employees(employee_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.employees` · 105행

기본키: employee_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `employee_id` | integer | 아니오 |
| `name` | character varying(50) | 아니오 |
| `job_id` | integer | 예 |
| `created_at` | timestamp with time zone | 예 |
| `is_degree_seeker` | boolean | 예 |
| `email` | character varying(255) | 예 |
| `department` | character varying(100) | 예 |
| `job_title` | character varying(100) | 예 |
| `grade` | character varying(50) | 예 |
| `source_type` | character varying(20) | 예 |
| `updated_at` | timestamp with time zone | 예 |
| `institution_id` | character varying(64) | 예 |
| `employee_number` | text | 예 |
| `password_hash` | text | 예 |
| `department_id` | bigint | 예 |
| `job_grade_id` | bigint | 예 |
| `is_department_head` | boolean | 아니오 |
| `hire_date` | date | 예 |
| `department_start_date` | date | 예 |
| `planned_project_description` | text | 예 |
| `unlisted_certifications` | text | 예 |

- FK `department_id, institution_id` → `public.departments(department_id, institution_id)`

- FK `job_grade_id, institution_id` → `public.job_grades(job_grade_id, institution_id)`

- FK `institution_id` → `public.institutions(institution_id)`

- FK `job_id` → `public.jobs(job_id)`

## `public.growth_reports` · 1행

기본키: report_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `report_id` | uuid | 아니오 |
| `project_id` | uuid | 아니오 |
| `report_type` | character varying(30) | 아니오 |
| `report_content` | jsonb | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `roadmap_id` | uuid | 아니오 |

- FK `project_id` → `public.projects(project_id)`

- FK `roadmap_id` → `public.roadmaps(roadmap_id)`

- FK `roadmap_id, project_id` → `public.roadmaps(roadmap_id, project_id)`

## `public.institutions` · 1행

기본키: institution_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `institution_id` | character varying(64) | 아니오 |
| `name` | character varying(255) | 아니오 |
| `external_code` | character varying(255) | 예 |
| `institution_code` | text | 예 |

## `public.job_grades` · 5행

기본키: job_grade_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `job_grade_id` | bigint | 아니오 |
| `institution_id` | character varying(64) | 아니오 |
| `name` | text | 아니오 |
| `sort_order` | integer | 아니오 |

- FK `institution_id` → `public.institutions(institution_id)`

## `public.job_skills` · 8행

기본키: job_id, skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `job_id` | integer | 아니오 |
| `skill_id` | integer | 아니오 |

- FK `job_id` → `public.jobs(job_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.jobs` · 6행

기본키: job_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `job_id` | integer | 아니오 |
| `title` | character varying(100) | 아니오 |
| `ncs_units` | text | 예 |
| `last_batch_updated` | timestamp with time zone | 예 |
| `record_source` | character varying(40) | 아니오 |
| `source_url` | text | 예 |
| `content_status` | text | 예 |
| `source_verified_at` | timestamp with time zone | 예 |
| `description` | text | 예 |

## `public.learning_resource_embeddings` · 2469행

기본키: resource_type, resource_id, embedding_model

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `resource_type` | text | 아니오 |
| `resource_id` | text | 아니오 |
| `embedding_model` | text | 아니오 |
| `dimensions` | integer | 아니오 |
| `input_version` | text | 아니오 |
| `input_sha256` | text | 아니오 |
| `embedding` | vector(1536) | 아니오 |
| `updated_at` | timestamp with time zone | 아니오 |
| `skill_id` | integer | 예 |
| `course_id` | character varying(255) | 예 |
| `isbn` | character varying(20) | 예 |
| `certification_id` | integer | 예 |
| `job_id` | integer | 예 |
| `major_id` | integer | 예 |

- FK `certification_id` → `public.certifications(cert_id)`

- FK `course_id` → `public.courses(course_id)`

- FK `isbn` → `public.books(isbn)`

- FK `job_id` → `public.jobs(job_id)`

- FK `major_id` → `public.majors(major_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.major_skills` · 14행

기본키: major_id, skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `major_id` | integer | 아니오 |
| `skill_id` | integer | 아니오 |

- FK `major_id` → `public.majors(major_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `public.majors` · 7행

기본키: major_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `major_id` | integer | 아니오 |
| `title` | character varying(100) | 아니오 |
| `curriculum` | text | 예 |
| `last_batch_updated` | timestamp with time zone | 예 |
| `source_url` | text | 예 |
| `content_status` | text | 예 |
| `source_verified_at` | timestamp with time zone | 예 |
| `description` | text | 예 |

## `public.projects` · 2행

기본키: project_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `project_id` | uuid | 아니오 |
| `employee_id` | integer | 아니오 |
| `project_name` | character varying(255) | 아니오 |
| `status` | character varying(50) | 아니오 |
| `current_stage` | integer | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `updated_at` | timestamp with time zone | 아니오 |
| `extracted_text` | text | 예 |
| `draft_plan` | text | 예 |
| `refined_plan` | text | 예 |
| `project_goal` | text | 예 |
| `project_scope` | text | 예 |
| `tech_stack` | jsonb | 아니오 |
| `milestones` | jsonb | 아니오 |
| `key_issues` | jsonb | 아니오 |
| `deliverables` | jsonb | 아니오 |
| `validation_criteria` | jsonb | 아니오 |
| `draft_conversations` | jsonb | 아니오 |
| `draft_choices` | jsonb | 아니오 |
| `draft_prompt_version_id` | uuid | 예 |
| `plan_prompt_version_id` | uuid | 예 |

- FK `draft_prompt_version_id` → `public.prompt_versions(prompt_version_id)`

- FK `plan_prompt_version_id` → `public.prompt_versions(prompt_version_id)`

- FK `employee_id` → `public.employees(employee_id)`

## `public.prompt_versions` · 6행

기본키: prompt_version_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `prompt_version_id` | uuid | 아니오 |
| `agent_id` | character varying(50) | 아니오 |
| `version_num` | integer | 아니오 |
| `system_prompt` | text | 아니오 |
| `is_active` | boolean | 아니오 |
| `parent_version_id` | uuid | 예 |
| `change_reason` | text | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `deactivated_at` | timestamp with time zone | 예 |

- FK `parent_version_id` → `public.prompt_versions(prompt_version_id)`

## `public.roadmap_comments` · 0행

기본키: comment_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `comment_id` | uuid | 아니오 |
| `roadmap_id` | uuid | 아니오 |
| `author_employee_id` | integer | 아니오 |
| `body` | text | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `updated_at` | timestamp with time zone | 아니오 |
| `modification_completed_at` | timestamp with time zone | 예 |

- FK `author_employee_id` → `public.employees(employee_id)`

- FK `roadmap_id` → `public.roadmaps(roadmap_id)`

## `public.roadmap_step_resources` · 1행

기본키: step_resource_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `step_resource_id` | bigint | 아니오 |
| `step_id` | uuid | 아니오 |
| `course_id` | character varying(255) | 예 |
| `isbn` | character varying(20) | 예 |
| `certification_id` | integer | 예 |

- FK `certification_id` → `public.certifications(cert_id)`

- FK `course_id` → `public.courses(course_id)`

- FK `isbn` → `public.books(isbn)`

- FK `step_id` → `public.roadmap_steps(step_id)`

## `public.roadmap_steps` · 3행

기본키: step_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `step_id` | uuid | 아니오 |
| `roadmap_id` | uuid | 아니오 |
| `step_order` | integer | 아니오 |
| `title` | text | 아니오 |
| `activity` | text | 예 |
| `estimated_duration` | text | 예 |
| `target_start_date` | date | 예 |
| `target_end_date` | date | 예 |
| `estimated_cost` | numeric(14,2) | 예 |
| `is_completed` | boolean | 아니오 |
| `completed_at` | timestamp with time zone | 예 |
| `details` | jsonb | 아니오 |

- FK `roadmap_id` → `public.roadmaps(roadmap_id)`

## `public.roadmaps` · 1행

기본키: roadmap_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `roadmap_id` | uuid | 아니오 |
| `project_id` | uuid | 아니오 |
| `strategy_type` | character varying(50) | 아니오 |
| `strategy_title` | character varying(255) | 예 |
| `summary` | text | 예 |
| `content` | jsonb | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `selected_at` | timestamp with time zone | 예 |
| `report_content` | jsonb | 예 |
| `baseline_content` | jsonb | 아니오 |
| `updated_at` | timestamp with time zone | 아니오 |
| `diagnostic_round_id` | uuid | 아니오 |
| `prompt_version_id` | uuid | 예 |

- FK `project_id` → `public.projects(project_id)`

- FK `diagnostic_round_id, project_id` → `public.diagnostic_rounds(diagnostic_round_id, project_id)`

- FK `prompt_version_id` → `public.prompt_versions(prompt_version_id)`

## `public.skill_tags` · 36행

기본키: skill_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `skill_id` | integer | 아니오 |
| `name` | character varying(50) | 아니오 |
| `category` | character varying(50) | 예 |

## `regulations.evaluation_item_definitions` · 70행

기본키: evaluation_item_definition_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `evaluation_item_definition_id` | character varying(64) | 아니오 |
| `evaluation_result_schema_id` | character varying(64) | 아니오 |
| `parent_item_id` | character varying(64) | 예 |
| `skill_id` | integer | 예 |
| `item_code` | character varying(255) | 아니오 |
| `item_name` | character varying(255) | 아니오 |
| `value_kind` | character varying(40) | 아니오 |
| `aggregation_role` | character varying(40) | 아니오 |
| `score_min` | numeric(12,3) | 예 |
| `score_max` | numeric(12,3) | 예 |
| `weight_percent` | numeric(6,3) | 예 |
| `unit` | character varying(40) | 예 |
| `scale_note` | text | 예 |
| `display_order` | integer | 아니오 |
| `definition_note` | text | 예 |

- FK `parent_item_id, evaluation_result_schema_id` → `regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id)`

- FK `evaluation_result_schema_id` → `regulations.evaluation_result_schemas(evaluation_result_schema_id)`

- FK `skill_id` → `public.skill_tags(skill_id)`

## `regulations.evaluation_result_schemas` · 11행

기본키: evaluation_result_schema_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `evaluation_result_schema_id` | character varying(64) | 아니오 |
| `institution_id` | character varying(64) | 아니오 |
| `schema_name` | character varying(255) | 아니오 |
| `version_label` | character varying(255) | 아니오 |
| `evaluation_kind` | character varying(40) | 아니오 |
| `applicability_condition` | jsonb | 아니오 |
| `applicability_note` | text | 예 |
| `effective_from` | date | 예 |
| `effective_to` | date | 예 |
| `rule_origin` | character varying(40) | 아니오 |
| `source_status` | character varying(40) | 아니오 |
| `review_status` | character varying(40) | 아니오 |
| `calculation_rule` | jsonb | 예 |
| `calculation_status` | character varying(40) | 아니오 |
| `source_note` | text | 예 |

- FK `institution_id` → `public.institutions(institution_id)`

## `regulations.evaluation_schema_sources` · 172행

기본키: evaluation_schema_source_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `evaluation_schema_source_id` | character varying(64) | 아니오 |
| `evaluation_result_schema_id` | character varying(64) | 아니오 |
| `evaluation_item_definition_id` | character varying(64) | 예 |
| `regulation_node_id` | character varying(64) | 아니오 |
| `source_role` | character varying(40) | 아니오 |
| `review_status` | character varying(40) | 아니오 |
| `source_note` | text | 예 |

- FK `evaluation_item_definition_id, evaluation_result_schema_id` → `regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id)`

- FK `regulation_node_id` → `regulations.regulation_nodes(regulation_node_id)`

- FK `evaluation_result_schema_id` → `regulations.evaluation_result_schemas(evaluation_result_schema_id)`

## `regulations.rag_chunk_embeddings` · 1410행

기본키: rag_chunk_id, embedding_model

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `rag_chunk_id` | character varying(64) | 아니오 |
| `embedding_model` | text | 아니오 |
| `dimensions` | integer | 아니오 |
| `input_version` | text | 아니오 |
| `input_sha256` | text | 아니오 |
| `embedding` | vector(1536) | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `updated_at` | timestamp with time zone | 아니오 |

- FK `rag_chunk_id` → `regulations.rag_chunks(rag_chunk_id)`

## `regulations.rag_chunk_sources` · 1774행

기본키: rag_chunk_source_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `rag_chunk_source_id` | character varying(64) | 아니오 |
| `rag_chunk_id` | character varying(64) | 아니오 |
| `regulation_node_id` | character varying(64) | 아니오 |
| `source_order` | integer | 아니오 |
| `source_role` | character varying(40) | 아니오 |
| `source_span` | jsonb | 예 |

- FK `rag_chunk_id` → `regulations.rag_chunks(rag_chunk_id)`

- FK `regulation_node_id` → `regulations.regulation_nodes(regulation_node_id)`

## `regulations.rag_chunks` · 1552행

기본키: rag_chunk_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `rag_chunk_id` | character varying(64) | 아니오 |
| `regulation_version_id` | character varying(64) | 아니오 |
| `chunk_text` | text | 아니오 |
| `chunk_type` | character varying(40) | 아니오 |
| `context_path` | character varying(1024) | 아니오 |
| `content_hash` | character varying(128) | 아니오 |
| `chunking_version` | character varying(255) | 아니오 |
| `index_revision` | character varying(255) | 아니오 |
| `embedding_model` | character varying(255) | 예 |
| `search_status` | character varying(40) | 아니오 |
| `created_at` | timestamp with time zone | 아니오 |
| `token_count` | integer | 예 |

- FK `regulation_version_id` → `regulations.regulation_versions(regulation_version_id)`

## `regulations.regulation_files` · 28행

기본키: regulation_file_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `regulation_file_id` | character varying(64) | 아니오 |
| `regulation_version_id` | character varying(64) | 아니오 |
| `source_file_id` | character varying(64) | 예 |
| `file_name` | character varying(255) | 아니오 |
| `file_format` | character varying(40) | 아니오 |
| `file_role` | character varying(40) | 아니오 |
| `storage_key` | character varying(2048) | 아니오 |
| `source_type` | character varying(40) | 아니오 |
| `source_url` | character varying(2048) | 예 |
| `retrieved_at` | timestamp with time zone | 아니오 |
| `file_hash` | character varying(128) | 아니오 |
| `is_extraction_source` | boolean | 아니오 |
| `parse_status` | character varying(40) | 아니오 |
| `access_level` | character varying(40) | 아니오 |

- FK `regulation_version_id` → `regulations.regulation_versions(regulation_version_id)`

- FK `source_file_id` → `regulations.regulation_files(regulation_file_id)`

## `regulations.regulation_nodes` · 3451행

기본키: regulation_node_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `regulation_node_id` | character varying(64) | 아니오 |
| `regulation_version_id` | character varying(64) | 아니오 |
| `regulation_file_id` | character varying(64) | 아니오 |
| `parent_node_id` | character varying(64) | 예 |
| `node_type` | character varying(40) | 아니오 |
| `label` | character varying(255) | 아니오 |
| `title` | character varying(255) | 예 |
| `path` | character varying(1024) | 아니오 |
| `display_order` | integer | 아니오 |
| `body_text` | text | 아니오 |
| `source_locator` | jsonb | 아니오 |
| `effective_from_override` | date | 예 |
| `effective_to_override` | date | 예 |
| `extraction_status` | character varying(40) | 아니오 |
| `review_note` | text | 예 |

- FK `parent_node_id` → `regulations.regulation_nodes(regulation_node_id)`

- FK `regulation_file_id` → `regulations.regulation_files(regulation_file_id)`

- FK `regulation_version_id` → `regulations.regulation_versions(regulation_version_id)`

## `regulations.regulation_references` · 462행

기본키: regulation_reference_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `regulation_reference_id` | character varying(64) | 아니오 |
| `regulation_node_id` | character varying(64) | 아니오 |
| `reference_type` | character varying(40) | 아니오 |
| `target_text` | text | 아니오 |
| `target_regulation_id` | character varying(64) | 예 |
| `target_version_id` | character varying(64) | 예 |
| `target_node_id` | character varying(64) | 예 |
| `resolution_status` | character varying(40) | 아니오 |
| `review_note` | text | 예 |

- FK `regulation_node_id` → `regulations.regulation_nodes(regulation_node_id)`

- FK `target_node_id` → `regulations.regulation_nodes(regulation_node_id)`

- FK `target_regulation_id` → `regulations.regulations(regulation_id)`

- FK `target_version_id` → `regulations.regulation_versions(regulation_version_id)`

## `regulations.regulation_scopes` · 389행

기본키: regulation_scope_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `regulation_scope_id` | character varying(64) | 아니오 |
| `regulation_node_id` | character varying(64) | 아니오 |
| `scope_type` | character varying(40) | 아니오 |
| `condition_text` | text | 아니오 |
| `condition_json` | jsonb | 예 |
| `applies_to_node_id` | character varying(64) | 예 |
| `review_status` | character varying(40) | 아니오 |

- FK `applies_to_node_id` → `regulations.regulation_nodes(regulation_node_id)`

- FK `regulation_node_id` → `regulations.regulation_nodes(regulation_node_id)`

## `regulations.regulation_versions` · 28행

기본키: regulation_version_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `regulation_version_id` | character varying(64) | 아니오 |
| `regulation_id` | character varying(64) | 아니오 |
| `version_label` | character varying(255) | 아니오 |
| `title_at_version` | character varying(255) | 아니오 |
| `content_kind` | character varying(40) | 아니오 |
| `coverage_status` | character varying(40) | 아니오 |
| `amendment_date` | date | 예 |
| `effective_from` | date | 예 |
| `effective_to` | date | 예 |
| `date_status` | character varying(40) | 아니오 |
| `review_status` | character varying(40) | 아니오 |
| `availability_status` | character varying(40) | 아니오 |
| `previous_version_id` | character varying(64) | 예 |
| `review_note` | text | 예 |

- FK `previous_version_id` → `regulations.regulation_versions(regulation_version_id)`

- FK `regulation_id` → `regulations.regulations(regulation_id)`

## `regulations.regulations` · 28행

기본키: regulation_id

| 컬럼 | 자료형 | NULL 허용 |
|---|---|---|
| `regulation_id` | character varying(64) | 아니오 |
| `institution_id` | character varying(64) | 아니오 |
| `name` | character varying(255) | 아니오 |
| `category` | character varying(40) | 아니오 |
| `document_kind` | character varying(40) | 아니오 |

- FK `institution_id` → `public.institutions(institution_id)`
