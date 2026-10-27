--
-- PostgreSQL database dump
--

\restrict 3tkaCs03LOEj7jFQz4ObFINgTYcVGV6czuGjz43SRDJZxfZGsAclBOIowU34wS7

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: extensions; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA extensions;


--
-- Name: growpath_legacy; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA growpath_legacy;


--
-- Name: growpath_meta; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA growpath_meta;


--
-- Name: hr_regulation_pilot; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA hr_regulation_pilot;


--
-- Name: knowledge; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA knowledge;


--
-- Name: regulations; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA regulations;


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: employee_can_read_project(integer, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.employee_can_read_project(actor integer, target uuid) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
 SELECT EXISTS(
  SELECT 1 FROM public.projects p JOIN public.employees owner ON owner.employee_id=p.employee_id
  JOIN public.employees viewer ON viewer.employee_id=actor
  WHERE p.project_id=target AND (owner.employee_id=actor OR
   (viewer.is_department_head AND viewer.institution_id=owner.institution_id AND EXISTS(
    WITH RECURSIVE tree AS (
     SELECT department_id FROM public.departments WHERE department_id=viewer.department_id
     UNION SELECT d.department_id FROM public.departments d JOIN tree x ON d.parent_department_id=x.department_id
    ) SELECT 1 FROM tree WHERE department_id=owner.department_id
   )))
 )
$$;


--
-- Name: guard_baseline_content(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.guard_baseline_content() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 IF NEW.baseline_content IS DISTINCT FROM OLD.baseline_content THEN RAISE EXCEPTION 'Baseline roadmap is immutable'; END IF;
 RETURN NEW;
END $$;


--
-- Name: guard_department_hierarchy(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.guard_department_hierarchy() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(763250131);
 IF NEW.parent_department_id IS NOT NULL AND EXISTS(
  WITH RECURSIVE ancestors AS (
   SELECT department_id,parent_department_id FROM public.departments WHERE department_id=NEW.parent_department_id
   UNION SELECT d.department_id,d.parent_department_id FROM public.departments d JOIN ancestors a ON d.department_id=a.parent_department_id
  ) SELECT 1 FROM ancestors WHERE department_id=NEW.department_id
 ) THEN RAISE EXCEPTION 'Department hierarchy cycle is not allowed'; END IF;
 RETURN NEW;
END $$;


--
-- Name: guard_growth_report(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.guard_growth_report() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'Completed growth reports are read-only'; END $$;


--
-- Name: guard_roadmap_comment(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.guard_roadmap_comment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE actor integer; pid uuid; author_id integer;
BEGIN
 -- A deleted parent permits its FK cascade; direct comment deletion still requires author context.
 IF TG_OP='DELETE' AND NOT EXISTS(SELECT 1 FROM public.roadmaps WHERE roadmap_id=OLD.roadmap_id) THEN RETURN OLD; END IF;
 actor:=nullif(current_setting('growpath.employee_id',true),'')::integer;
 IF actor IS NULL THEN RAISE EXCEPTION 'Authenticated employee context is required'; END IF;
 author_id:=CASE WHEN TG_OP='DELETE' THEN OLD.author_employee_id ELSE NEW.author_employee_id END;
 IF actor<>author_id THEN RAISE EXCEPTION 'Only the comment author may write, edit or delete it'; END IF;
 IF TG_OP='UPDATE' AND (NEW.author_employee_id<>OLD.author_employee_id OR NEW.roadmap_id<>OLD.roadmap_id) THEN RAISE EXCEPTION 'Comment author and roadmap cannot change'; END IF;
 SELECT project_id INTO pid FROM public.roadmaps WHERE roadmap_id=CASE WHEN TG_OP='DELETE' THEN OLD.roadmap_id ELSE NEW.roadmap_id END;
 IF NOT EXISTS(SELECT 1 FROM public.employees WHERE employee_id=actor AND is_department_head) OR NOT public.employee_can_read_project(actor,pid) THEN RAISE EXCEPTION 'Department-head scope is required'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 NEW.updated_at:=now();RETURN NEW;
END $$;


--
-- Name: mark_roadmap_comments_modified(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.mark_roadmap_comments_modified() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE rid uuid;
BEGIN
 IF TG_TABLE_NAME='roadmaps' THEN
  IF NEW.content IS NOT DISTINCT FROM OLD.content THEN RETURN NEW; END IF;
  IF NEW.baseline_content IS DISTINCT FROM OLD.baseline_content THEN RAISE EXCEPTION 'Baseline roadmap is immutable'; END IF;
  rid:=NEW.roadmap_id;
 ELSIF TG_TABLE_NAME='roadmap_steps' THEN
  IF (to_jsonb(NEW)-'is_completed'-'completed_at') IS NOT DISTINCT FROM (to_jsonb(OLD)-'is_completed'-'completed_at') THEN RETURN NEW; END IF;
  rid:=NEW.roadmap_id;
 END IF;
 UPDATE public.roadmap_comments SET modification_completed_at=now() WHERE roadmap_id=rid AND created_at<=now();
 RETURN NEW;
END $$;


--
-- Name: synchronize_step_completion(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.synchronize_step_completion() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 IF NEW.is_completed THEN NEW.completed_at:=coalesce(NEW.completed_at,now()); ELSE NEW.completed_at:=NULL; END IF;
 RETURN NEW;
END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_generations; Type: TABLE; Schema: growpath_legacy; Owner: -
--

CREATE TABLE growpath_legacy.agent_generations (
    generation_id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL,
    agent_id character varying(50) NOT NULL,
    prompt_version_id uuid,
    provider character varying(50) NOT NULL,
    model character varying(100) NOT NULL,
    roadmap_content jsonb NOT NULL,
    summary text NOT NULL,
    latency_ms integer NOT NULL,
    status character varying(20) DEFAULT 'SUCCESS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT agent_generations_agent_id_check CHECK (((agent_id)::text = ANY (ARRAY[('agent_practical'::character varying)::text, ('agent_certified'::character varying)::text, ('agent_fasttrack'::character varying)::text]))),
    CONSTRAINT agent_generations_status_check CHECK (((status)::text = ANY (ARRAY[('SUCCESS'::character varying)::text, ('FAILED'::character varying)::text, ('TIMEOUT'::character varying)::text])))
);


--
-- Name: TABLE agent_generations; Type: COMMENT; Schema: growpath_legacy; Owner: -
--

COMMENT ON TABLE growpath_legacy.agent_generations IS 'Historical workflow archive; retained with data and FK identity. Not a live application master.';


--
-- Name: agent_selections; Type: TABLE; Schema: growpath_legacy; Owner: -
--

CREATE TABLE growpath_legacy.agent_selections (
    selection_id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL,
    chosen_generation_id uuid NOT NULL,
    chosen_agent_id character varying(50) NOT NULL,
    selection_reason text,
    user_type character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT agent_selections_chosen_agent_id_check CHECK (((chosen_agent_id)::text = ANY (ARRAY[('agent_practical'::character varying)::text, ('agent_certified'::character varying)::text, ('agent_fasttrack'::character varying)::text]))),
    CONSTRAINT agent_selections_user_type_check CHECK (((user_type)::text = ANY (ARRAY[('REAL_USER'::character varying)::text, ('TEST_MANUAL'::character varying)::text, ('TEST_AUTO'::character varying)::text])))
);


--
-- Name: TABLE agent_selections; Type: COMMENT; Schema: growpath_legacy; Owner: -
--

COMMENT ON TABLE growpath_legacy.agent_selections IS 'Historical workflow archive; retained with data and FK identity. Not a live application master.';


--
-- Name: finetuning_datasets; Type: TABLE; Schema: growpath_legacy; Owner: -
--

CREATE TABLE growpath_legacy.finetuning_datasets (
    dataset_id uuid DEFAULT gen_random_uuid() NOT NULL,
    dataset_type character varying(20) NOT NULL,
    record_count integer NOT NULL,
    export_path text NOT NULL,
    pii_masked boolean DEFAULT true NOT NULL,
    filter_criteria jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT finetuning_datasets_dataset_type_check CHECK (((dataset_type)::text = ANY (ARRAY[('SFT_JSONL'::character varying)::text, ('DPO_JSONL'::character varying)::text, ('HF_DATASET'::character varying)::text])))
);


--
-- Name: TABLE finetuning_datasets; Type: COMMENT; Schema: growpath_legacy; Owner: -
--

COMMENT ON TABLE growpath_legacy.finetuning_datasets IS 'Historical workflow archive; retained with data and FK identity. Not a live application master.';


--
-- Name: preference_pairs; Type: TABLE; Schema: growpath_legacy; Owner: -
--

CREATE TABLE growpath_legacy.preference_pairs (
    pair_id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL,
    chosen_generation_id uuid NOT NULL,
    rejected_generation_id uuid NOT NULL,
    prompt_input jsonb NOT NULL,
    chosen_output jsonb NOT NULL,
    rejected_output jsonb NOT NULL,
    user_type character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT preference_pairs_user_type_check CHECK (((user_type)::text = ANY (ARRAY[('REAL_USER'::character varying)::text, ('TEST_MANUAL'::character varying)::text, ('TEST_AUTO'::character varying)::text])))
);


--
-- Name: TABLE preference_pairs; Type: COMMENT; Schema: growpath_legacy; Owner: -
--

COMMENT ON TABLE growpath_legacy.preference_pairs IS 'Historical workflow archive; retained with data and FK identity. Not a live application master.';


--
-- Name: roadmap_requests; Type: TABLE; Schema: growpath_legacy; Owner: -
--

CREATE TABLE growpath_legacy.roadmap_requests (
    request_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_type character varying(20) NOT NULL,
    employee_id character varying(64),
    raw_user_prompt text NOT NULL,
    conversation_history jsonb DEFAULT '[]'::jsonb NOT NULL,
    user_requirements jsonb DEFAULT '{}'::jsonb NOT NULL,
    retrieved_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT roadmap_requests_user_type_check CHECK (((user_type)::text = ANY (ARRAY[('REAL_USER'::character varying)::text, ('TEST_MANUAL'::character varying)::text, ('TEST_AUTO'::character varying)::text])))
);


--
-- Name: TABLE roadmap_requests; Type: COMMENT; Schema: growpath_legacy; Owner: -
--

COMMENT ON TABLE growpath_legacy.roadmap_requests IS 'Historical workflow archive; retained with data and FK identity. Not a live application master.';


--
-- Name: test_mock_profiles; Type: TABLE; Schema: growpath_legacy; Owner: -
--

CREATE TABLE growpath_legacy.test_mock_profiles (
    profile_id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_type character varying(20) NOT NULL,
    profile_name character varying(100) NOT NULL,
    department character varying(100) NOT NULL,
    grade character varying(50) NOT NULL,
    job_title character varying(100) NOT NULL,
    career_years integer NOT NULL,
    current_skills jsonb NOT NULL,
    target_skills jsonb NOT NULL,
    work_context_summary text NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT test_mock_profiles_source_type_check CHECK (((source_type)::text = ANY (ARRAY[('TEST_MANUAL'::character varying)::text, ('TEST_AUTO'::character varying)::text])))
);


--
-- Name: TABLE test_mock_profiles; Type: COMMENT; Schema: growpath_legacy; Owner: -
--

COMMENT ON TABLE growpath_legacy.test_mock_profiles IS 'Historical workflow archive; retained with data and FK identity. Not a live application master.';


--
-- Name: catalog_api_sources; Type: TABLE; Schema: growpath_meta; Owner: -
--

CREATE TABLE growpath_meta.catalog_api_sources (
    resource_type text NOT NULL,
    source text NOT NULL,
    external_key text NOT NULL,
    entity_key text NOT NULL,
    payload jsonb NOT NULL,
    mapping_evidence jsonb NOT NULL,
    fetched_at timestamp with time zone NOT NULL
);


--
-- Name: schema_migrations; Type: TABLE; Schema: growpath_meta; Owner: -
--

CREATE TABLE growpath_meta.schema_migrations (
    version text NOT NULL,
    sha256 text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: evaluation_item_definitions; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.evaluation_item_definitions (
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
    definition_note text
);


--
-- Name: evaluation_item_definition; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.evaluation_item_definition AS
 SELECT evaluation_item_definition_id,
    evaluation_result_schema_id,
    parent_item_id,
    skill_id,
    item_code,
    item_name,
    value_kind,
    aggregation_role,
    score_min,
    score_max,
    weight_percent,
    unit,
    scale_note,
    display_order,
    definition_note
   FROM regulations.evaluation_item_definitions;


--
-- Name: evaluation_result_schemas; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.evaluation_result_schemas (
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
    source_note text
);


--
-- Name: evaluation_result_schema; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.evaluation_result_schema AS
 SELECT evaluation_result_schema_id,
    institution_id,
    schema_name,
    version_label,
    evaluation_kind,
    applicability_condition,
    applicability_note,
    effective_from,
    effective_to,
    rule_origin,
    source_status,
    review_status,
    calculation_rule,
    calculation_status,
    source_note
   FROM regulations.evaluation_result_schemas;


--
-- Name: evaluation_schema_sources; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.evaluation_schema_sources (
    evaluation_schema_source_id character varying(64) NOT NULL,
    evaluation_result_schema_id character varying(64) NOT NULL,
    evaluation_item_definition_id character varying(64),
    regulation_node_id character varying(64) NOT NULL,
    source_role character varying(40) NOT NULL,
    review_status character varying(40) NOT NULL,
    source_note text
);


--
-- Name: evaluation_schema_source; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.evaluation_schema_source AS
 SELECT evaluation_schema_source_id,
    evaluation_result_schema_id,
    evaluation_item_definition_id,
    regulation_node_id,
    source_role,
    review_status,
    source_note
   FROM regulations.evaluation_schema_sources;


--
-- Name: institutions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.institutions (
    institution_id character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    external_code character varying(255),
    institution_code text GENERATED ALWAYS AS (COALESCE(external_code, institution_id)) STORED
);


--
-- Name: institution; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.institution AS
 SELECT institution_id,
    name,
    external_code,
    institution_code
   FROM public.institutions;


--
-- Name: rag_chunks; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.rag_chunks (
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
    token_count integer
);


--
-- Name: rag_chunk; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.rag_chunk AS
 SELECT rag_chunk_id,
    regulation_version_id,
    chunk_text,
    chunk_type,
    context_path,
    content_hash,
    chunking_version,
    index_revision,
    embedding_model,
    search_status,
    created_at,
    token_count
   FROM regulations.rag_chunks;


--
-- Name: rag_chunk_embeddings; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.rag_chunk_embeddings (
    rag_chunk_id character varying(64) NOT NULL,
    embedding_model text NOT NULL,
    dimensions integer NOT NULL,
    input_version text NOT NULL,
    input_sha256 text NOT NULL,
    embedding public.vector(1536) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT rag_chunk_embedding_dimensions_check CHECK ((dimensions = 1536)),
    CONSTRAINT rag_chunk_embedding_embedding_check CHECK ((public.vector_norm(embedding) > (0)::double precision)),
    CONSTRAINT rag_chunk_embedding_input_sha256_check CHECK ((length(input_sha256) = 64))
);


--
-- Name: rag_chunk_embedding; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.rag_chunk_embedding AS
 SELECT rag_chunk_id,
    embedding_model,
    dimensions,
    input_version,
    input_sha256,
    embedding,
    created_at,
    updated_at
   FROM regulations.rag_chunk_embeddings;


--
-- Name: rag_chunk_sources; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.rag_chunk_sources (
    rag_chunk_source_id character varying(64) NOT NULL,
    rag_chunk_id character varying(64) NOT NULL,
    regulation_node_id character varying(64) NOT NULL,
    source_order integer NOT NULL,
    source_role character varying(40) NOT NULL,
    source_span jsonb
);


--
-- Name: rag_chunk_source; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.rag_chunk_source AS
 SELECT rag_chunk_source_id,
    rag_chunk_id,
    regulation_node_id,
    source_order,
    source_role,
    source_span
   FROM regulations.rag_chunk_sources;


--
-- Name: regulations; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.regulations (
    regulation_id character varying(64) NOT NULL,
    institution_id character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    category character varying(40) NOT NULL,
    document_kind character varying(40) NOT NULL
);


--
-- Name: regulation; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.regulation AS
 SELECT regulation_id,
    institution_id,
    name,
    category,
    document_kind
   FROM regulations.regulations;


--
-- Name: regulation_files; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.regulation_files (
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
    access_level character varying(40) NOT NULL
);


--
-- Name: regulation_file; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.regulation_file AS
 SELECT regulation_file_id,
    regulation_version_id,
    source_file_id,
    file_name,
    file_format,
    file_role,
    storage_key,
    source_type,
    source_url,
    retrieved_at,
    file_hash,
    is_extraction_source,
    parse_status,
    access_level
   FROM regulations.regulation_files;


--
-- Name: regulation_nodes; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.regulation_nodes (
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
    review_note text
);


--
-- Name: regulation_node; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.regulation_node AS
 SELECT regulation_node_id,
    regulation_version_id,
    regulation_file_id,
    parent_node_id,
    node_type,
    label,
    title,
    path,
    display_order,
    body_text,
    source_locator,
    effective_from_override,
    effective_to_override,
    extraction_status,
    review_note
   FROM regulations.regulation_nodes;


--
-- Name: regulation_references; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.regulation_references (
    regulation_reference_id character varying(64) NOT NULL,
    regulation_node_id character varying(64) NOT NULL,
    reference_type character varying(40) NOT NULL,
    target_text text NOT NULL,
    target_regulation_id character varying(64),
    target_version_id character varying(64),
    target_node_id character varying(64),
    resolution_status character varying(40) NOT NULL,
    review_note text
);


--
-- Name: regulation_reference; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.regulation_reference AS
 SELECT regulation_reference_id,
    regulation_node_id,
    reference_type,
    target_text,
    target_regulation_id,
    target_version_id,
    target_node_id,
    resolution_status,
    review_note
   FROM regulations.regulation_references;


--
-- Name: regulation_scopes; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.regulation_scopes (
    regulation_scope_id character varying(64) NOT NULL,
    regulation_node_id character varying(64) NOT NULL,
    scope_type character varying(40) NOT NULL,
    condition_text text NOT NULL,
    condition_json jsonb,
    applies_to_node_id character varying(64),
    review_status character varying(40) NOT NULL
);


--
-- Name: regulation_scope; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.regulation_scope AS
 SELECT regulation_scope_id,
    regulation_node_id,
    scope_type,
    condition_text,
    condition_json,
    applies_to_node_id,
    review_status
   FROM regulations.regulation_scopes;


--
-- Name: regulation_versions; Type: TABLE; Schema: regulations; Owner: -
--

CREATE TABLE regulations.regulation_versions (
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
    review_note text
);


--
-- Name: regulation_version; Type: VIEW; Schema: hr_regulation_pilot; Owner: -
--

CREATE VIEW hr_regulation_pilot.regulation_version AS
 SELECT regulation_version_id,
    regulation_id,
    version_label,
    title_at_version,
    content_kind,
    coverage_status,
    amendment_date,
    effective_from,
    effective_to,
    date_status,
    review_status,
    availability_status,
    previous_version_id,
    review_note
   FROM regulations.regulation_versions;


--
-- Name: chunks; Type: TABLE; Schema: knowledge; Owner: -
--

CREATE TABLE knowledge.chunks (
    chunk_id text NOT NULL,
    document_id text NOT NULL,
    display_order integer NOT NULL,
    chunk_text text NOT NULL,
    chunk_text_sha256 text NOT NULL,
    is_virtual boolean NOT NULL,
    metadata jsonb NOT NULL,
    embedding_model text,
    dimensions integer,
    input_sha256 text,
    embedding public.vector(1536),
    embedded_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chunks_check CHECK ((chunk_text_sha256 = encode(sha256(convert_to(chunk_text, 'UTF8'::name)), 'hex'::text))),
    CONSTRAINT chunks_check1 CHECK ((((embedding IS NULL) AND (embedding_model IS NULL) AND (dimensions IS NULL) AND (input_sha256 IS NULL) AND (embedded_at IS NULL)) OR ((embedding IS NOT NULL) AND (embedding_model IS NOT NULL) AND (dimensions IS NOT NULL) AND (input_sha256 IS NOT NULL) AND (embedded_at IS NOT NULL) AND (embedding_model = 'text-embedding-3-small'::text) AND (dimensions = 1536) AND (public.vector_norm(embedding) > (0)::double precision) AND (input_sha256 = chunk_text_sha256)))),
    CONSTRAINT chunks_chunk_text_check CHECK ((length(chunk_text) > 0)),
    CONSTRAINT chunks_chunk_text_sha256_check CHECK ((chunk_text_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT chunks_display_order_check CHECK ((display_order > 0)),
    CONSTRAINT chunks_metadata_check CHECK ((jsonb_typeof(metadata) = 'object'::text))
);


--
-- Name: TABLE chunks; Type: COMMENT; Schema: knowledge; Owner: -
--

COMMENT ON TABLE knowledge.chunks IS 'Verbatim supplied chunks and original provenance. is_virtual must accompany retrieval results.';


--
-- Name: documents; Type: TABLE; Schema: knowledge; Owner: -
--

CREATE TABLE knowledge.documents (
    document_id text NOT NULL,
    category text NOT NULL,
    title text NOT NULL,
    document_kind text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT documents_category_check CHECK ((category = ANY (ARRAY['수자원공사 정보'::text, '사내 생활안내'::text]))),
    CONSTRAINT documents_document_kind_check CHECK ((document_kind = ANY (ARRAY['report'::text, 'plan'::text, 'web_page'::text, 'guide'::text]))),
    CONSTRAINT documents_title_check CHECK ((length(title) > 0))
);


--
-- Name: TABLE documents; Type: COMMENT; Schema: knowledge; Owner: -
--

COMMENT ON TABLE knowledge.documents IS 'Company information and synthetic workplace guides; category is required by the search API.';


--
-- Name: assessment_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessment_questions (
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
    CONSTRAINT assessment_questions_assessment_type_check CHECK (((assessment_type)::text = ANY (ARRAY[('PRE'::character varying)::text, ('POST'::character varying)::text])))
);


--
-- Name: assessment_responses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessment_responses (
    response_id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    question_id uuid NOT NULL,
    assessment_type character varying(20) NOT NULL,
    selected_option text NOT NULL,
    score integer NOT NULL,
    answered_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT assessment_responses_assessment_type_check CHECK (((assessment_type)::text = ANY (ARRAY[('PRE'::character varying)::text, ('POST'::character varying)::text]))),
    CONSTRAINT assessment_responses_score_check CHECK (((score >= 1) AND (score <= 5)))
);


--
-- Name: book_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.book_skills (
    isbn character varying(20) NOT NULL,
    skill_id integer NOT NULL
);


--
-- Name: book_skill_map; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.book_skill_map AS
 SELECT isbn,
    skill_id
   FROM public.book_skills;


--
-- Name: books; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.books (
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
    ai_mention text
);


--
-- Name: COLUMN books.ai_mention; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.books.ai_mention IS '향후 AI 생성 도서 요약. 현재 미생성 NULL';


--
-- Name: certification_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.certification_skills (
    cert_id integer NOT NULL,
    skill_id integer NOT NULL
);


--
-- Name: cert_skill_map; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.cert_skill_map AS
 SELECT cert_id,
    skill_id
   FROM public.certification_skills;


--
-- Name: certifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.certifications (
    cert_id integer NOT NULL,
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
    ai_mention text
);


--
-- Name: COLUMN certifications.ai_mention; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.certifications.ai_mention IS '향후 AI 생성 자격증 요약. 현재 미생성 NULL';


--
-- Name: certifications_cert_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.certifications_cert_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: certifications_cert_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.certifications_cert_id_seq OWNED BY public.certifications.cert_id;


--
-- Name: courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.courses (
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
    enrollment_start timestamp with time zone,
    enrollment_end timestamp with time zone,
    enrollment_period_type text DEFAULT 'unknown'::text NOT NULL,
    ai_mention text,
    CONSTRAINT chk_courses_difficulty CHECK (((difficulty)::text = ANY (ARRAY[('BEGINNER'::character varying)::text, ('INTERMEDIATE'::character varying)::text, ('ADVANCED'::character varying)::text]))),
    CONSTRAINT courses_enrollment_order_check CHECK (((enrollment_start IS NULL) OR (enrollment_end IS NULL) OR (enrollment_start <= enrollment_end))),
    CONSTRAINT courses_enrollment_type_check CHECK ((enrollment_period_type = ANY (ARRAY['scheduled'::text, 'unrestricted'::text, 'unknown'::text]))),
    CONSTRAINT courses_enrollment_values_check CHECK ((((enrollment_period_type = 'scheduled'::text) AND (enrollment_start IS NOT NULL) AND (enrollment_end IS NOT NULL)) OR ((enrollment_period_type = 'unrestricted'::text) AND (enrollment_start IS NULL) AND (enrollment_end IS NULL)) OR (enrollment_period_type = 'unknown'::text)))
);


--
-- Name: COLUMN courses.enrollment_start; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.courses.enrollment_start IS '수강신청 시작 시각. UTC 저장, Asia/Seoul 표시';


--
-- Name: COLUMN courses.enrollment_end; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.courses.enrollment_end IS '수강신청 종료 시각. 종료 시각까지 신청 가능';


--
-- Name: COLUMN courses.enrollment_period_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.courses.enrollment_period_type IS 'scheduled=기간 지정, unrestricted=기간 제한 없음, unknown=기간 확인 필요';


--
-- Name: COLUMN courses.ai_mention; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.courses.ai_mention IS '향후 AI 생성 강좌 요약. 현재 미생성 NULL';


--
-- Name: course_availability; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.course_availability WITH (security_invoker='true') AS
 SELECT course_id,
    title,
    category_name,
    org_name,
    url,
    is_matchup,
    cost,
    duration_weeks,
    recruitment_status,
    syllabus_summary,
    last_batch_updated,
    platform,
    difficulty,
    record_source,
    source_url,
    content_status,
    source_verified_at,
    image_url,
    enrollment_start,
    enrollment_end,
    enrollment_period_type,
        CASE
            WHEN (enrollment_period_type = 'unrestricted'::text) THEN 'ongoing'::text
            WHEN (enrollment_period_type <> 'scheduled'::text) THEN NULL::text
            WHEN (CURRENT_TIMESTAMP < enrollment_start) THEN 'upcoming'::text
            WHEN (CURRENT_TIMESTAMP <= enrollment_end) THEN 'ongoing'::text
            ELSE 'ended'::text
        END AS enrollment_status,
        CASE
            WHEN (enrollment_period_type = 'unrestricted'::text) THEN '기간 제한 없음'::text
            WHEN (enrollment_period_type <> 'scheduled'::text) THEN '기간 확인 필요'::text
            WHEN (CURRENT_TIMESTAMP < enrollment_start) THEN '예정'::text
            WHEN (CURRENT_TIMESTAMP <= enrollment_end) THEN '진행중'::text
            ELSE '종료'::text
        END AS enrollment_status_label
   FROM public.courses c;


--
-- Name: course_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.course_skills (
    course_id character varying(50) NOT NULL,
    skill_id integer NOT NULL
);


--
-- Name: course_skill_map; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.course_skill_map AS
 SELECT course_id,
    skill_id
   FROM public.course_skills;


--
-- Name: departments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.departments (
    department_id bigint NOT NULL,
    institution_id character varying(64) NOT NULL,
    department_code text NOT NULL,
    name text NOT NULL,
    parent_department_id bigint,
    CONSTRAINT departments_check CHECK ((parent_department_id IS DISTINCT FROM department_id))
);


--
-- Name: departments_department_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.departments ALTER COLUMN department_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.departments_department_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: diagnostic_rounds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_rounds (
    diagnostic_round_id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    round_number integer NOT NULL,
    project_snapshot jsonb NOT NULL,
    agent_input jsonb,
    diagnostic_result jsonb,
    pre_completed_at timestamp with time zone,
    post_completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT diagnostic_rounds_round_number_check CHECK ((round_number > 0))
);


--
-- Name: employee_certifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_certifications (
    employee_id integer NOT NULL,
    certification_id integer NOT NULL
);


--
-- Name: employee_education_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_education_records (
    education_record_id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id integer NOT NULL,
    school_name text NOT NULL,
    education_level text NOT NULL,
    department_name text,
    major_id integer,
    enrollment_date date,
    graduation_date date,
    CONSTRAINT employee_education_dates_order CHECK (((enrollment_date IS NULL) OR (graduation_date IS NULL) OR (graduation_date >= enrollment_date))),
    CONSTRAINT employee_education_records_education_level_check CHECK ((education_level = ANY (ARRAY['middle_school_or_lower'::text, 'high_school'::text, 'associate'::text, 'bachelor'::text, 'master'::text, 'doctorate'::text, 'other'::text]))),
    CONSTRAINT employee_education_records_school_name_check CHECK ((length(TRIM(BOTH FROM school_name)) > 0))
);


--
-- Name: COLUMN employee_education_records.enrollment_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.employee_education_records.enrollment_date IS '입학일. 시트 입학일과 매핑. 정확한 날짜 미확인 시 NULL; 연도로 날짜를 추정하지 않음.';


--
-- Name: COLUMN employee_education_records.graduation_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.employee_education_records.graduation_date IS '졸업일. 시트 졸업일과 매핑. 재학 중 또는 정확한 날짜 미확인 시 NULL.';


--
-- Name: employee_input_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_input_profiles (
    employee_id integer NOT NULL,
    experience_summary text,
    development_years numeric(6,2),
    technology_experience text,
    project_experience text,
    learning_history text,
    learning_preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    submission_note text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT employee_input_profiles_development_years_check CHECK (((development_years >= (0)::numeric) AND (development_years <> 'NaN'::numeric))),
    CONSTRAINT employee_input_profiles_learning_preferences_check CHECK ((jsonb_typeof(learning_preferences) = 'object'::text))
);


--
-- Name: TABLE employee_input_profiles; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.employee_input_profiles IS 'Employee form extension restored after the 20261026 snapshot; original user-entered experience and preferences only.';


--
-- Name: employee_recommended_prompts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_recommended_prompts (
    prompt_id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id integer,
    prompt_text text,
    display_order smallint,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT employee_recommended_prompts_display_order_check CHECK (((display_order >= 1) AND (display_order <= 3))),
    CONSTRAINT employee_recommended_prompts_prompt_text_check CHECK (((prompt_text IS NULL) OR (length(btrim(prompt_text)) > 0)))
);


--
-- Name: TABLE employee_recommended_prompts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.employee_recommended_prompts IS 'Optional latest employee growth questions; up to three ordered slots per employee.';


--
-- Name: employee_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_skills (
    employee_id integer NOT NULL,
    skill_id integer NOT NULL
);


--
-- Name: employees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employees (
    employee_id integer NOT NULL,
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
    hire_date date,
    department_start_date date,
    planned_project_description text,
    unlisted_certifications text,
    CONSTRAINT employees_department_requires_institution CHECK (((department_id IS NULL) OR (institution_id IS NOT NULL))),
    CONSTRAINT employees_department_start_after_hire CHECK (((hire_date IS NULL) OR (department_start_date IS NULL) OR (department_start_date >= hire_date))),
    CONSTRAINT employees_grade_requires_institution CHECK (((job_grade_id IS NULL) OR (institution_id IS NOT NULL))),
    CONSTRAINT employees_head_department_required CHECK (((NOT is_department_head) OR (department_id IS NOT NULL))),
    CONSTRAINT employees_password_is_hash CHECK (((password_hash IS NULL) OR (password_hash ~~ '$argon2id$%%'::text))),
    CONSTRAINT employees_planned_project_description_nonblank CHECK (((planned_project_description IS NULL) OR (length(btrim(planned_project_description)) > 0))),
    CONSTRAINT employees_unlisted_certifications_nonblank CHECK (((unlisted_certifications IS NULL) OR (length(btrim(unlisted_certifications)) > 0)))
);


--
-- Name: COLUMN employees.hire_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.employees.hire_date IS '입사일. 미확인 시 NULL';


--
-- Name: COLUMN employees.department_start_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.employees.department_start_date IS '현재 부서 배치 시작일. 미확인 시 NULL';


--
-- Name: COLUMN employees.planned_project_description; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.employees.planned_project_description IS '설문 이전 추천 질문 생성용 본인 업무·구상 중인 프로젝트 설명. 시트 본인 업무 설명과 매핑. 미입력 시 NULL. 생성된 질문이나 확정 프로젝트 계획이 아님.';


--
-- Name: COLUMN employees.unlisted_certifications; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.employees.unlisted_certifications IS '직원이 입력한 미등재 보유 자격 원문(자격명/발급기관/취득일). 시트 목록에 없는 자격과 매핑. 미입력 NULL. 검증된 자격 마스터 또는 보유 FK를 자동 생성하지 않음.';


--
-- Name: growth_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_reports (
    report_id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    report_type character varying(30) DEFAULT 'PRE_POST'::character varying NOT NULL,
    report_content jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    roadmap_id uuid NOT NULL
);


--
-- Name: job_grades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_grades (
    job_grade_id bigint NOT NULL,
    institution_id character varying(64) NOT NULL,
    name text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL
);


--
-- Name: job_grades_job_grade_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.job_grades ALTER COLUMN job_grade_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.job_grades_job_grade_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: job_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_skills (
    job_id integer NOT NULL,
    skill_id integer NOT NULL
);


--
-- Name: job_skill_map; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.job_skill_map AS
 SELECT job_id,
    skill_id
   FROM public.job_skills;


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    job_id integer NOT NULL,
    title character varying(100) NOT NULL,
    ncs_units text,
    last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    record_source character varying(40) DEFAULT 'EXTERNAL_INGESTION'::character varying NOT NULL,
    source_url text,
    content_status text,
    source_verified_at timestamp with time zone,
    description text
);


--
-- Name: learning_resource_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.learning_resource_embeddings (
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    embedding_model text NOT NULL,
    dimensions integer NOT NULL,
    input_version text NOT NULL,
    input_sha256 text NOT NULL,
    embedding public.vector(1536) NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    skill_id integer,
    course_id character varying(255),
    isbn character varying(20),
    certification_id integer,
    job_id integer,
    major_id integer,
    CONSTRAINT learning_resource_embedding_dimensions_check CHECK ((dimensions = 1536)),
    CONSTRAINT learning_resource_embedding_embedding_check CHECK ((public.vector_norm(embedding) > (0)::double precision)),
    CONSTRAINT learning_resource_embedding_input_sha256_check CHECK ((length(input_sha256) = 64)),
    CONSTRAINT resource_kind_check CHECK ((resource_type = ANY (ARRAY['skills'::text, 'courses'::text, 'books'::text, 'certifications'::text, 'jobs'::text, 'majors'::text]))),
    CONSTRAINT vector_one_source CHECK ((num_nonnulls(skill_id, course_id, isbn, certification_id, job_id, major_id) = 1)),
    CONSTRAINT vector_source_matches_key CHECK ((((resource_type = 'skills'::text) AND ((skill_id)::text = resource_id)) OR ((resource_type = 'courses'::text) AND ((course_id)::text = resource_id)) OR ((resource_type = 'books'::text) AND ((isbn)::text = resource_id)) OR ((resource_type = 'certifications'::text) AND ((certification_id)::text = resource_id)) OR ((resource_type = 'jobs'::text) AND ((job_id)::text = resource_id)) OR ((resource_type = 'majors'::text) AND ((major_id)::text = resource_id)))),
    CONSTRAINT vector_type_matches_source CHECK (
CASE resource_type
    WHEN 'skills'::text THEN (skill_id IS NOT NULL)
    WHEN 'courses'::text THEN (course_id IS NOT NULL)
    WHEN 'books'::text THEN (isbn IS NOT NULL)
    WHEN 'certifications'::text THEN (certification_id IS NOT NULL)
    WHEN 'jobs'::text THEN (job_id IS NOT NULL)
    WHEN 'majors'::text THEN (major_id IS NOT NULL)
    ELSE false
END)
);


--
-- Name: learning_resource_embedding; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.learning_resource_embedding AS
 SELECT resource_type,
    resource_id,
    embedding_model,
    dimensions,
    input_version,
    input_sha256,
    embedding,
    updated_at,
    skill_id,
    course_id,
    isbn,
    certification_id,
    job_id,
    major_id
   FROM public.learning_resource_embeddings;


--
-- Name: major_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.major_skills (
    major_id integer NOT NULL,
    skill_id integer NOT NULL
);


--
-- Name: major_skill_map; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.major_skill_map AS
 SELECT major_id,
    skill_id
   FROM public.major_skills;


--
-- Name: majors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.majors (
    major_id integer NOT NULL,
    title character varying(100) NOT NULL,
    curriculum text,
    last_batch_updated timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    source_url text,
    content_status text,
    source_verified_at timestamp with time zone,
    description text
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
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
    draft_prompt_version_id uuid,
    plan_prompt_version_id uuid
);


--
-- Name: project_plans; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.project_plans AS
 SELECT project_id AS plan_id,
    project_id AS session_id,
    draft_plan,
    refined_plan,
    project_goal,
    project_scope,
    tech_stack,
    milestones,
    key_issues,
    deliverables,
    validation_criteria,
    created_at,
    updated_at
   FROM public.projects;


--
-- Name: prompt_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prompt_versions (
    prompt_version_id uuid DEFAULT gen_random_uuid() NOT NULL,
    agent_id character varying(50) NOT NULL,
    version_num integer NOT NULL,
    system_prompt text NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    parent_version_id uuid,
    change_reason text NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    deactivated_at timestamp with time zone,
    CONSTRAINT prompt_versions_agent_id_check CHECK (((agent_id)::text = ANY (ARRAY[('agent_practical'::character varying)::text, ('agent_certified'::character varying)::text, ('agent_fasttrack'::character varying)::text, ('agent_plan_draft'::character varying)::text, ('agent_plan_refine'::character varying)::text])))
);


--
-- Name: roadmap_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roadmap_comments (
    comment_id uuid DEFAULT gen_random_uuid() NOT NULL,
    roadmap_id uuid NOT NULL,
    author_employee_id integer NOT NULL,
    body text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    modification_completed_at timestamp with time zone,
    CONSTRAINT roadmap_comments_body_check CHECK ((length(TRIM(BOTH FROM body)) > 0))
);


--
-- Name: roadmap_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roadmap_steps (
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
    CONSTRAINT roadmap_steps_check CHECK (((target_end_date IS NULL) OR (target_start_date IS NULL) OR (target_end_date >= target_start_date))),
    CONSTRAINT roadmap_steps_check1 CHECK ((is_completed = (completed_at IS NOT NULL))),
    CONSTRAINT roadmap_steps_estimated_cost_check CHECK ((estimated_cost >= (0)::numeric)),
    CONSTRAINT roadmap_steps_step_order_check CHECK ((step_order > 0))
);


--
-- Name: roadmaps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roadmaps (
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
    prompt_version_id uuid
);


--
-- Name: roadmap_progress; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.roadmap_progress AS
 SELECT m.roadmap_id,
    count(s.step_id) AS total_steps,
    count(s.step_id) FILTER (WHERE s.is_completed) AS completed_steps,
        CASE
            WHEN (count(s.step_id) = 0) THEN (0)::numeric
            ELSE round(((100.0 * (count(s.step_id) FILTER (WHERE s.is_completed))::numeric) / (count(s.step_id))::numeric), 2)
        END AS progress_percent
   FROM (public.roadmaps m
     LEFT JOIN public.roadmap_steps s USING (roadmap_id))
  GROUP BY m.roadmap_id;


--
-- Name: roadmap_sessions; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.roadmap_sessions AS
 SELECT project_id AS session_id,
    employee_id AS user_id,
    project_name,
    status,
    current_stage,
    created_at,
    updated_at
   FROM public.projects;


--
-- Name: roadmap_step_resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roadmap_step_resources (
    step_resource_id bigint NOT NULL,
    step_id uuid NOT NULL,
    course_id character varying(255),
    isbn character varying(20),
    certification_id integer,
    CONSTRAINT roadmap_step_resources_check CHECK ((num_nonnulls(course_id, isbn, certification_id) = 1))
);


--
-- Name: roadmap_step_resources_step_resource_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.roadmap_step_resources ALTER COLUMN step_resource_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.roadmap_step_resources_step_resource_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: skill_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_tags (
    skill_id integer NOT NULL,
    name character varying(50) NOT NULL,
    category character varying(50) DEFAULT 'IT/Tech'::character varying
);


--
-- Name: skill_tags_skill_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.skill_tags_skill_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: skill_tags_skill_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.skill_tags_skill_id_seq OWNED BY public.skill_tags.skill_id;


--
-- Name: users; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.users AS
 SELECT employee_id AS user_id,
    name,
    job_id AS target_job_id,
    created_at,
    is_degree_seeker,
    email,
    department,
    job_title,
    grade,
    source_type,
    updated_at
   FROM public.employees;


--
-- Name: users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_user_id_seq OWNED BY public.employees.employee_id;


--
-- Name: certifications cert_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certifications ALTER COLUMN cert_id SET DEFAULT nextval('public.certifications_cert_id_seq'::regclass);


--
-- Name: employees employee_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees ALTER COLUMN employee_id SET DEFAULT nextval('public.users_user_id_seq'::regclass);


--
-- Name: skill_tags skill_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_tags ALTER COLUMN skill_id SET DEFAULT nextval('public.skill_tags_skill_id_seq'::regclass);


--
-- Name: agent_generations agent_generations_pkey; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_generations
    ADD CONSTRAINT agent_generations_pkey PRIMARY KEY (generation_id);


--
-- Name: agent_selections agent_selections_pkey; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_selections
    ADD CONSTRAINT agent_selections_pkey PRIMARY KEY (selection_id);


--
-- Name: agent_selections agent_selections_request_id_key; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_selections
    ADD CONSTRAINT agent_selections_request_id_key UNIQUE (request_id);


--
-- Name: finetuning_datasets finetuning_datasets_pkey; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.finetuning_datasets
    ADD CONSTRAINT finetuning_datasets_pkey PRIMARY KEY (dataset_id);


--
-- Name: preference_pairs preference_pairs_pkey; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.preference_pairs
    ADD CONSTRAINT preference_pairs_pkey PRIMARY KEY (pair_id);


--
-- Name: roadmap_requests roadmap_requests_pkey; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.roadmap_requests
    ADD CONSTRAINT roadmap_requests_pkey PRIMARY KEY (request_id);


--
-- Name: test_mock_profiles test_mock_profiles_pkey; Type: CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.test_mock_profiles
    ADD CONSTRAINT test_mock_profiles_pkey PRIMARY KEY (profile_id);


--
-- Name: catalog_api_sources catalog_api_sources_pkey; Type: CONSTRAINT; Schema: growpath_meta; Owner: -
--

ALTER TABLE ONLY growpath_meta.catalog_api_sources
    ADD CONSTRAINT catalog_api_sources_pkey PRIMARY KEY (resource_type, source, external_key);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: growpath_meta; Owner: -
--

ALTER TABLE ONLY growpath_meta.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: chunks chunks_document_id_display_order_key; Type: CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.chunks
    ADD CONSTRAINT chunks_document_id_display_order_key UNIQUE (document_id, display_order);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (chunk_id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (document_id);


--
-- Name: assessment_questions assessment_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_questions
    ADD CONSTRAINT assessment_questions_pkey PRIMARY KEY (question_id);


--
-- Name: growth_reports assessment_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_reports
    ADD CONSTRAINT assessment_reports_pkey PRIMARY KEY (report_id);


--
-- Name: assessment_responses assessment_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_responses
    ADD CONSTRAINT assessment_responses_pkey PRIMARY KEY (response_id);


--
-- Name: assessment_questions assessment_sequence_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_questions
    ADD CONSTRAINT assessment_sequence_unique UNIQUE (diagnostic_round_id, assessment_type, sequence_no);


--
-- Name: book_skills book_skill_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.book_skills
    ADD CONSTRAINT book_skill_map_pkey PRIMARY KEY (isbn, skill_id);


--
-- Name: books books_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.books
    ADD CONSTRAINT books_pkey PRIMARY KEY (isbn);


--
-- Name: certification_skills cert_skill_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certification_skills
    ADD CONSTRAINT cert_skill_map_pkey PRIMARY KEY (cert_id, skill_id);


--
-- Name: certifications certifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certifications
    ADD CONSTRAINT certifications_pkey PRIMARY KEY (cert_id);


--
-- Name: certifications certifications_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certifications
    ADD CONSTRAINT certifications_title_key UNIQUE (title);


--
-- Name: course_skills course_skill_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_skills
    ADD CONSTRAINT course_skill_map_pkey PRIMARY KEY (course_id, skill_id);


--
-- Name: courses courses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (course_id);


--
-- Name: departments departments_department_id_institution_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_department_id_institution_id_key UNIQUE (department_id, institution_id);


--
-- Name: departments departments_institution_id_department_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_institution_id_department_code_key UNIQUE (institution_id, department_code);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (department_id);


--
-- Name: diagnostic_rounds diagnostic_rounds_diagnostic_round_id_project_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_rounds
    ADD CONSTRAINT diagnostic_rounds_diagnostic_round_id_project_id_key UNIQUE (diagnostic_round_id, project_id);


--
-- Name: diagnostic_rounds diagnostic_rounds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_rounds
    ADD CONSTRAINT diagnostic_rounds_pkey PRIMARY KEY (diagnostic_round_id);


--
-- Name: diagnostic_rounds diagnostic_rounds_project_id_round_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_rounds
    ADD CONSTRAINT diagnostic_rounds_project_id_round_number_key UNIQUE (project_id, round_number);


--
-- Name: employee_certifications employee_certifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_certifications
    ADD CONSTRAINT employee_certifications_pkey PRIMARY KEY (employee_id, certification_id);


--
-- Name: employee_education_records employee_education_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_education_records
    ADD CONSTRAINT employee_education_records_pkey PRIMARY KEY (education_record_id);


--
-- Name: employee_input_profiles employee_input_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_input_profiles
    ADD CONSTRAINT employee_input_profiles_pkey PRIMARY KEY (employee_id);


--
-- Name: employee_recommended_prompts employee_recommended_prompts_employee_order_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_recommended_prompts
    ADD CONSTRAINT employee_recommended_prompts_employee_order_key UNIQUE (employee_id, display_order);


--
-- Name: employee_recommended_prompts employee_recommended_prompts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_recommended_prompts
    ADD CONSTRAINT employee_recommended_prompts_pkey PRIMARY KEY (prompt_id);


--
-- Name: employee_skills employee_skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_skills
    ADD CONSTRAINT employee_skills_pkey PRIMARY KEY (employee_id, skill_id);


--
-- Name: employees employees_number_required; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.employees
    ADD CONSTRAINT employees_number_required CHECK (((employee_number IS NOT NULL) AND (employee_number !~ '^[[:space:]]*$'::text))) NOT VALID;


--
-- Name: employees employees_number_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_number_unique UNIQUE (institution_id, employee_number);


--
-- Name: growth_reports growth_roadmap_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_reports
    ADD CONSTRAINT growth_roadmap_unique UNIQUE (roadmap_id);


--
-- Name: institutions institution_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institutions
    ADD CONSTRAINT institution_pkey PRIMARY KEY (institution_id);


--
-- Name: institutions institutions_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institutions
    ADD CONSTRAINT institutions_code_unique UNIQUE (institution_code);


--
-- Name: job_grades job_grades_institution_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_grades
    ADD CONSTRAINT job_grades_institution_id_name_key UNIQUE (institution_id, name);


--
-- Name: job_grades job_grades_job_grade_id_institution_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_grades
    ADD CONSTRAINT job_grades_job_grade_id_institution_id_key UNIQUE (job_grade_id, institution_id);


--
-- Name: job_grades job_grades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_grades
    ADD CONSTRAINT job_grades_pkey PRIMARY KEY (job_grade_id);


--
-- Name: job_skills job_skill_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_skills
    ADD CONSTRAINT job_skill_map_pkey PRIMARY KEY (job_id, skill_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (job_id);


--
-- Name: learning_resource_embeddings learning_resource_embedding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embedding_pkey PRIMARY KEY (resource_type, resource_id, embedding_model);


--
-- Name: major_skills major_skill_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.major_skills
    ADD CONSTRAINT major_skill_map_pkey PRIMARY KEY (major_id, skill_id);


--
-- Name: majors majors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.majors
    ADD CONSTRAINT majors_pkey PRIMARY KEY (major_id);


--
-- Name: prompt_versions prompt_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_versions
    ADD CONSTRAINT prompt_versions_pkey PRIMARY KEY (prompt_version_id);


--
-- Name: roadmap_comments roadmap_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_comments
    ADD CONSTRAINT roadmap_comments_pkey PRIMARY KEY (comment_id);


--
-- Name: roadmaps roadmap_diagnostic_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT roadmap_diagnostic_unique UNIQUE (diagnostic_round_id);


--
-- Name: roadmaps roadmap_generations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT roadmap_generations_pkey PRIMARY KEY (roadmap_id);


--
-- Name: roadmaps roadmap_project_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT roadmap_project_identity UNIQUE (roadmap_id, project_id);


--
-- Name: projects roadmap_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT roadmap_sessions_pkey PRIMARY KEY (project_id);


--
-- Name: roadmap_step_resources roadmap_step_resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_pkey PRIMARY KEY (step_resource_id);


--
-- Name: roadmap_step_resources roadmap_step_resources_step_id_certification_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_step_id_certification_id_key UNIQUE (step_id, certification_id);


--
-- Name: roadmap_step_resources roadmap_step_resources_step_id_course_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_step_id_course_id_key UNIQUE (step_id, course_id);


--
-- Name: roadmap_step_resources roadmap_step_resources_step_id_isbn_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_step_id_isbn_key UNIQUE (step_id, isbn);


--
-- Name: roadmap_steps roadmap_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_steps
    ADD CONSTRAINT roadmap_steps_pkey PRIMARY KEY (step_id);


--
-- Name: roadmap_steps roadmap_steps_roadmap_id_step_order_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_steps
    ADD CONSTRAINT roadmap_steps_roadmap_id_step_order_key UNIQUE (roadmap_id, step_order);


--
-- Name: skill_tags skill_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_tags
    ADD CONSTRAINT skill_tags_pkey PRIMARY KEY (skill_id);


--
-- Name: skill_tags skill_tags_skill_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_tags
    ADD CONSTRAINT skill_tags_skill_name_key UNIQUE (name);


--
-- Name: prompt_versions uq_agent_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_versions
    ADD CONSTRAINT uq_agent_version UNIQUE (agent_id, version_num);


--
-- Name: assessment_questions uq_assessment_question_scope; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_questions
    ADD CONSTRAINT uq_assessment_question_scope UNIQUE (question_id, project_id, assessment_type);


--
-- Name: roadmaps uq_generation_scope; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT uq_generation_scope UNIQUE (roadmap_id, project_id);


--
-- Name: growth_reports uq_session_assessment_report; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_reports
    ADD CONSTRAINT uq_session_assessment_report UNIQUE (project_id);


--
-- Name: assessment_responses uq_session_question_resp; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_responses
    ADD CONSTRAINT uq_session_question_resp UNIQUE (project_id, question_id);


--
-- Name: employees users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT users_pkey PRIMARY KEY (employee_id);


--
-- Name: evaluation_item_definitions evaluation_item_definition_id_schema_uq; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_item_definitions
    ADD CONSTRAINT evaluation_item_definition_id_schema_uq UNIQUE (evaluation_item_definition_id, evaluation_result_schema_id);


--
-- Name: evaluation_item_definitions evaluation_item_definition_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_item_definitions
    ADD CONSTRAINT evaluation_item_definition_pkey PRIMARY KEY (evaluation_item_definition_id);


--
-- Name: evaluation_item_definitions evaluation_item_definition_schema_code_uq; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_item_definitions
    ADD CONSTRAINT evaluation_item_definition_schema_code_uq UNIQUE (evaluation_result_schema_id, item_code);


--
-- Name: evaluation_result_schemas evaluation_result_schema_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_result_schemas
    ADD CONSTRAINT evaluation_result_schema_pkey PRIMARY KEY (evaluation_result_schema_id);


--
-- Name: evaluation_schema_sources evaluation_schema_source_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_schema_sources
    ADD CONSTRAINT evaluation_schema_source_pkey PRIMARY KEY (evaluation_schema_source_id);


--
-- Name: rag_chunk_embeddings rag_chunk_embedding_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunk_embeddings
    ADD CONSTRAINT rag_chunk_embedding_pkey PRIMARY KEY (rag_chunk_id, embedding_model);


--
-- Name: rag_chunks rag_chunk_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunks
    ADD CONSTRAINT rag_chunk_pkey PRIMARY KEY (rag_chunk_id);


--
-- Name: rag_chunk_sources rag_chunk_source_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunk_sources
    ADD CONSTRAINT rag_chunk_source_pkey PRIMARY KEY (rag_chunk_source_id);


--
-- Name: rag_chunk_sources rag_chunk_source_rag_chunk_id_source_order_key; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunk_sources
    ADD CONSTRAINT rag_chunk_source_rag_chunk_id_source_order_key UNIQUE (rag_chunk_id, source_order);


--
-- Name: regulation_files regulation_file_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_files
    ADD CONSTRAINT regulation_file_pkey PRIMARY KEY (regulation_file_id);


--
-- Name: regulation_nodes regulation_node_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_nodes
    ADD CONSTRAINT regulation_node_pkey PRIMARY KEY (regulation_node_id);


--
-- Name: regulations regulation_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulations
    ADD CONSTRAINT regulation_pkey PRIMARY KEY (regulation_id);


--
-- Name: regulation_references regulation_reference_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_references
    ADD CONSTRAINT regulation_reference_pkey PRIMARY KEY (regulation_reference_id);


--
-- Name: regulation_scopes regulation_scope_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_scopes
    ADD CONSTRAINT regulation_scope_pkey PRIMARY KEY (regulation_scope_id);


--
-- Name: regulation_versions regulation_version_pkey; Type: CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_versions
    ADD CONSTRAINT regulation_version_pkey PRIMARY KEY (regulation_version_id);


--
-- Name: idx_agent_generations_agent_id; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_agent_generations_agent_id ON growpath_legacy.agent_generations USING btree (agent_id);


--
-- Name: idx_agent_generations_request_id; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_agent_generations_request_id ON growpath_legacy.agent_generations USING btree (request_id);


--
-- Name: idx_agent_selections_chosen_agent; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_agent_selections_chosen_agent ON growpath_legacy.agent_selections USING btree (chosen_agent_id);


--
-- Name: idx_agent_selections_user_type; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_agent_selections_user_type ON growpath_legacy.agent_selections USING btree (user_type);


--
-- Name: idx_preference_pairs_request; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_preference_pairs_request ON growpath_legacy.preference_pairs USING btree (request_id);


--
-- Name: idx_preference_pairs_user_type; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_preference_pairs_user_type ON growpath_legacy.preference_pairs USING btree (user_type);


--
-- Name: idx_roadmap_requests_created_at; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_roadmap_requests_created_at ON growpath_legacy.roadmap_requests USING btree (created_at DESC);


--
-- Name: idx_roadmap_requests_user_type; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX idx_roadmap_requests_user_type ON growpath_legacy.roadmap_requests USING btree (user_type);


--
-- Name: ix_fk_158874b9f83bbe9b; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_158874b9f83bbe9b ON growpath_legacy.agent_generations USING btree (prompt_version_id);


--
-- Name: ix_fk_15a5ebe4dfc75e2b; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_15a5ebe4dfc75e2b ON growpath_legacy.agent_selections USING btree (request_id);


--
-- Name: ix_fk_599ec525ba60e8e7; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_599ec525ba60e8e7 ON growpath_legacy.agent_selections USING btree (chosen_generation_id);


--
-- Name: ix_fk_6b45655c45d7b24d; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_6b45655c45d7b24d ON growpath_legacy.agent_generations USING btree (request_id);


--
-- Name: ix_fk_a53fd571f0cfab46; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_a53fd571f0cfab46 ON growpath_legacy.preference_pairs USING btree (chosen_generation_id);


--
-- Name: ix_fk_d0e9836cf2249867; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_d0e9836cf2249867 ON growpath_legacy.preference_pairs USING btree (rejected_generation_id);


--
-- Name: ix_fk_fc600f1452d43da7; Type: INDEX; Schema: growpath_legacy; Owner: -
--

CREATE INDEX ix_fk_fc600f1452d43da7 ON growpath_legacy.preference_pairs USING btree (request_id);


--
-- Name: knowledge_document_category_idx; Type: INDEX; Schema: knowledge; Owner: -
--

CREATE INDEX knowledge_document_category_idx ON knowledge.documents USING btree (category);


--
-- Name: employees_one_department_head; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX employees_one_department_head ON public.employees USING btree (department_id) WHERE is_department_head;


--
-- Name: idx_book_skill_map_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_book_skill_map_skill_id ON public.book_skills USING btree (skill_id);


--
-- Name: idx_books_loan_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_books_loan_count ON public.books USING btree (loan_count DESC);


--
-- Name: idx_bootstrap_assessment_questions; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bootstrap_assessment_questions ON public.assessment_questions USING btree (project_id, assessment_type, sequence_no);


--
-- Name: idx_bootstrap_assessment_responses; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bootstrap_assessment_responses ON public.assessment_responses USING btree (project_id, assessment_type);


--
-- Name: idx_bootstrap_roadmap_sessions; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bootstrap_roadmap_sessions ON public.projects USING btree (employee_id, status);


--
-- Name: idx_cert_skill_map_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cert_skill_map_skill_id ON public.certification_skills USING btree (skill_id);


--
-- Name: idx_course_skill_map_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_course_skill_map_skill_id ON public.course_skills USING btree (skill_id);


--
-- Name: idx_job_skill_map_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_skill_map_skill_id ON public.job_skills USING btree (skill_id);


--
-- Name: idx_major_skill_map_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_major_skill_map_skill_id ON public.major_skills USING btree (skill_id);


--
-- Name: idx_users_email_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_email_unique ON public.employees USING btree (email);


--
-- Name: ix_fk_01ef474ad445cc8a; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_01ef474ad445cc8a ON public.book_skills USING btree (isbn);


--
-- Name: ix_fk_0ceb3d40d3bb9ae5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_0ceb3d40d3bb9ae5 ON public.diagnostic_rounds USING btree (project_id);


--
-- Name: ix_fk_12758341d20b2513; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_12758341d20b2513 ON public.roadmap_steps USING btree (roadmap_id);


--
-- Name: ix_fk_181303b24c703c0d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_181303b24c703c0d ON public.course_skills USING btree (skill_id);


--
-- Name: ix_fk_1ab2fbba1829760d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_1ab2fbba1829760d ON public.employee_skills USING btree (employee_id);


--
-- Name: ix_fk_1b81411b3e29f35a; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_1b81411b3e29f35a ON public.course_skills USING btree (course_id);


--
-- Name: ix_fk_25d6e76c74913375; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_25d6e76c74913375 ON public.book_skills USING btree (skill_id);


--
-- Name: ix_fk_28a14420fc1cd839; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_28a14420fc1cd839 ON public.departments USING btree (parent_department_id, institution_id);


--
-- Name: ix_fk_2e391a37ccd3ab18; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_2e391a37ccd3ab18 ON public.employee_certifications USING btree (employee_id);


--
-- Name: ix_fk_2ff1bf7cadabb534; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_2ff1bf7cadabb534 ON public.major_skills USING btree (skill_id);


--
-- Name: ix_fk_319c6b90abd2610d; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_319c6b90abd2610d ON public.certification_skills USING btree (skill_id);


--
-- Name: ix_fk_32fd25b28e8fc1d1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_32fd25b28e8fc1d1 ON public.roadmap_step_resources USING btree (certification_id);


--
-- Name: ix_fk_34098b3ca7781be1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_34098b3ca7781be1 ON public.learning_resource_embeddings USING btree (certification_id);


--
-- Name: ix_fk_35fb774e5b80967e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_35fb774e5b80967e ON public.assessment_responses USING btree (question_id, project_id, assessment_type);


--
-- Name: ix_fk_3a419b49b03de17f; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_3a419b49b03de17f ON public.learning_resource_embeddings USING btree (major_id);


--
-- Name: ix_fk_3a98788b55be7504; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_3a98788b55be7504 ON public.growth_reports USING btree (roadmap_id, project_id);


--
-- Name: ix_fk_3bb3ff734d031b46; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_3bb3ff734d031b46 ON public.learning_resource_embeddings USING btree (job_id);


--
-- Name: ix_fk_43a42c7b11e880f4; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_43a42c7b11e880f4 ON public.employees USING btree (department_id, institution_id);


--
-- Name: ix_fk_47e0bc8906606651; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_47e0bc8906606651 ON public.job_skills USING btree (skill_id);


--
-- Name: ix_fk_4ad66d1ab54cb86b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_4ad66d1ab54cb86b ON public.employee_education_records USING btree (employee_id);


--
-- Name: ix_fk_4b50a78ae0ee0183; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_4b50a78ae0ee0183 ON public.learning_resource_embeddings USING btree (isbn);


--
-- Name: ix_fk_4f60ef49313180b1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_4f60ef49313180b1 ON public.learning_resource_embeddings USING btree (course_id);


--
-- Name: ix_fk_57c0f60b2bc70a94; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_57c0f60b2bc70a94 ON public.employees USING btree (job_id);


--
-- Name: ix_fk_5ce87b96164ebea5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_5ce87b96164ebea5 ON public.assessment_questions USING btree (project_id);


--
-- Name: ix_fk_78edc2cbae8c546b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_78edc2cbae8c546b ON public.growth_reports USING btree (roadmap_id);


--
-- Name: ix_fk_808cdf5523cbaa0a; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_808cdf5523cbaa0a ON public.learning_resource_embeddings USING btree (skill_id);


--
-- Name: ix_fk_84dbe690e325064e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_84dbe690e325064e ON public.departments USING btree (institution_id);


--
-- Name: ix_fk_8ca40bb78e281caf; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_8ca40bb78e281caf ON public.assessment_questions USING btree (skill_id);


--
-- Name: ix_fk_8d69dd77542db035; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_8d69dd77542db035 ON public.roadmaps USING btree (diagnostic_round_id, project_id);


--
-- Name: ix_fk_934fc63891756448; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_934fc63891756448 ON public.major_skills USING btree (major_id);


--
-- Name: ix_fk_93b61f1b4363ff08; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_93b61f1b4363ff08 ON public.assessment_questions USING btree (diagnostic_round_id, project_id);


--
-- Name: ix_fk_94e53f2167c63619; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_94e53f2167c63619 ON public.growth_reports USING btree (project_id);


--
-- Name: ix_fk_97421a7762504701; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_97421a7762504701 ON public.projects USING btree (employee_id);


--
-- Name: ix_fk_abb0309000bbd715; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_abb0309000bbd715 ON public.certification_skills USING btree (cert_id);


--
-- Name: ix_fk_af56223fa742e5f5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_af56223fa742e5f5 ON public.assessment_responses USING btree (project_id);


--
-- Name: ix_fk_b063a27880fef73c; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_b063a27880fef73c ON public.job_skills USING btree (job_id);


--
-- Name: ix_fk_b41406d8cca862e2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_b41406d8cca862e2 ON public.roadmap_step_resources USING btree (isbn);


--
-- Name: ix_fk_b4af19c67e190ca6; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_b4af19c67e190ca6 ON public.employee_certifications USING btree (certification_id);


--
-- Name: ix_fk_b99b4f809f112e4c; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_b99b4f809f112e4c ON public.employee_education_records USING btree (major_id);


--
-- Name: ix_fk_ba6126f935dec4a5; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_ba6126f935dec4a5 ON public.roadmaps USING btree (project_id);


--
-- Name: ix_fk_beb2f8c6838ebb2b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_beb2f8c6838ebb2b ON public.employees USING btree (institution_id);


--
-- Name: ix_fk_d00f9fbf28b6ecac; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_d00f9fbf28b6ecac ON public.prompt_versions USING btree (parent_version_id);


--
-- Name: ix_fk_d30d13fd16cf22ca; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_d30d13fd16cf22ca ON public.employee_skills USING btree (skill_id);


--
-- Name: ix_fk_dd0d21641e38f132; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_dd0d21641e38f132 ON public.roadmap_comments USING btree (author_employee_id);


--
-- Name: ix_fk_df4b1c9873040faa; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_df4b1c9873040faa ON public.job_grades USING btree (institution_id);


--
-- Name: ix_fk_e01485ee152e4869; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_e01485ee152e4869 ON public.roadmap_step_resources USING btree (course_id);


--
-- Name: ix_fk_e25a3b98eacfcda7; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_e25a3b98eacfcda7 ON public.employees USING btree (job_grade_id, institution_id);


--
-- Name: ix_fk_ec808dff6e0f967f; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_ec808dff6e0f967f ON public.roadmap_step_resources USING btree (step_id);


--
-- Name: ix_fk_edb9d0c5f190e5d9; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fk_edb9d0c5f190e5d9 ON public.roadmap_comments USING btree (roadmap_id);


--
-- Name: projects_draft_prompt_version_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX projects_draft_prompt_version_idx ON public.projects USING btree (draft_prompt_version_id);


--
-- Name: projects_plan_prompt_version_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX projects_plan_prompt_version_idx ON public.projects USING btree (plan_prompt_version_id);


--
-- Name: roadmaps_prompt_version_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX roadmaps_prompt_version_idx ON public.roadmaps USING btree (prompt_version_id);


--
-- Name: uq_active_agent_prompt; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_active_agent_prompt ON public.prompt_versions USING btree (agent_id) WHERE (is_active = true);


--
-- Name: ix_fk_03450ea79fe0b774; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_03450ea79fe0b774 ON regulations.rag_chunk_sources USING btree (regulation_node_id);


--
-- Name: ix_fk_04a6ffe0a05f06eb; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_04a6ffe0a05f06eb ON regulations.regulation_references USING btree (regulation_node_id);


--
-- Name: ix_fk_0cc89b78cb9643d6; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_0cc89b78cb9643d6 ON regulations.regulation_files USING btree (source_file_id);


--
-- Name: ix_fk_118528e91e4ff85b; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_118528e91e4ff85b ON regulations.evaluation_item_definitions USING btree (evaluation_result_schema_id);


--
-- Name: ix_fk_183730ca30bb1c86; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_183730ca30bb1c86 ON regulations.regulation_nodes USING btree (regulation_file_id);


--
-- Name: ix_fk_2a0e395b63357436; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_2a0e395b63357436 ON regulations.regulation_scopes USING btree (applies_to_node_id);


--
-- Name: ix_fk_2de99a5ae9c2798a; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_2de99a5ae9c2798a ON regulations.regulation_references USING btree (target_node_id);


--
-- Name: ix_fk_31496077ba621bf3; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_31496077ba621bf3 ON regulations.regulation_references USING btree (target_version_id);


--
-- Name: ix_fk_32fd6b25e31704c8; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_32fd6b25e31704c8 ON regulations.regulation_nodes USING btree (regulation_version_id);


--
-- Name: ix_fk_3937b5193d9b773b; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_3937b5193d9b773b ON regulations.rag_chunk_sources USING btree (rag_chunk_id);


--
-- Name: ix_fk_3b32deff056db58c; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_3b32deff056db58c ON regulations.regulation_versions USING btree (previous_version_id);


--
-- Name: ix_fk_4142ab72eb856638; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_4142ab72eb856638 ON regulations.regulation_files USING btree (regulation_version_id);


--
-- Name: ix_fk_4f8c89ffa74e9ff1; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_4f8c89ffa74e9ff1 ON regulations.evaluation_item_definitions USING btree (skill_id);


--
-- Name: ix_fk_4fbae23a0d48c2e4; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_4fbae23a0d48c2e4 ON regulations.evaluation_schema_sources USING btree (regulation_node_id);


--
-- Name: ix_fk_696e87e79751722f; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_696e87e79751722f ON regulations.rag_chunk_embeddings USING btree (rag_chunk_id);


--
-- Name: ix_fk_963597d9a5f4cb47; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_963597d9a5f4cb47 ON regulations.regulation_versions USING btree (regulation_id);


--
-- Name: ix_fk_a128e14f5c20e49c; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_a128e14f5c20e49c ON regulations.regulation_references USING btree (target_regulation_id);


--
-- Name: ix_fk_a7cc3400d23cb8cc; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_a7cc3400d23cb8cc ON regulations.evaluation_schema_sources USING btree (evaluation_result_schema_id);


--
-- Name: ix_fk_c05c181ea2ae730c; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_c05c181ea2ae730c ON regulations.regulation_nodes USING btree (parent_node_id);


--
-- Name: ix_fk_d83085f3211be167; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_d83085f3211be167 ON regulations.regulations USING btree (institution_id);


--
-- Name: ix_fk_dd3e51a020b5939d; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_dd3e51a020b5939d ON regulations.regulation_scopes USING btree (regulation_node_id);


--
-- Name: ix_fk_ed417aa36e905597; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_ed417aa36e905597 ON regulations.evaluation_item_definitions USING btree (parent_item_id, evaluation_result_schema_id);


--
-- Name: ix_fk_f37be8315243ce42; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_f37be8315243ce42 ON regulations.evaluation_result_schemas USING btree (institution_id);


--
-- Name: ix_fk_fa906d4c5759e118; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_fa906d4c5759e118 ON regulations.rag_chunks USING btree (regulation_version_id);


--
-- Name: ix_fk_fcd8aee13008e3d1; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX ix_fk_fcd8aee13008e3d1 ON regulations.evaluation_schema_sources USING btree (evaluation_item_definition_id, evaluation_result_schema_id);


--
-- Name: rag_chunk_embedding_model_idx; Type: INDEX; Schema: regulations; Owner: -
--

CREATE INDEX rag_chunk_embedding_model_idx ON regulations.rag_chunk_embeddings USING btree (embedding_model);


--
-- Name: roadmap_comments comment_author_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER comment_author_guard BEFORE INSERT OR DELETE OR UPDATE OF body, author_employee_id, roadmap_id ON public.roadmap_comments FOR EACH ROW EXECUTE FUNCTION public.guard_roadmap_comment();


--
-- Name: departments department_hierarchy_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER department_hierarchy_guard BEFORE INSERT OR UPDATE OF parent_department_id, institution_id ON public.departments FOR EACH ROW EXECUTE FUNCTION public.guard_department_hierarchy();


--
-- Name: growth_reports growth_report_readonly; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER growth_report_readonly BEFORE UPDATE ON public.growth_reports FOR EACH ROW EXECUTE FUNCTION public.guard_growth_report();


--
-- Name: roadmaps roadmap_baseline_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER roadmap_baseline_guard BEFORE UPDATE OF baseline_content ON public.roadmaps FOR EACH ROW EXECUTE FUNCTION public.guard_baseline_content();


--
-- Name: roadmaps roadmap_comment_resolution; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER roadmap_comment_resolution AFTER UPDATE OF content ON public.roadmaps FOR EACH ROW EXECUTE FUNCTION public.mark_roadmap_comments_modified();


--
-- Name: roadmap_steps step_comment_resolution; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER step_comment_resolution AFTER UPDATE ON public.roadmap_steps FOR EACH ROW EXECUTE FUNCTION public.mark_roadmap_comments_modified();


--
-- Name: roadmap_steps step_completion_time; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER step_completion_time BEFORE INSERT OR UPDATE OF is_completed ON public.roadmap_steps FOR EACH ROW EXECUTE FUNCTION public.synchronize_step_completion();


--
-- Name: agent_generations agent_generations_prompt_version_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_generations
    ADD CONSTRAINT agent_generations_prompt_version_id_fkey FOREIGN KEY (prompt_version_id) REFERENCES public.prompt_versions(prompt_version_id);


--
-- Name: agent_generations agent_generations_request_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_generations
    ADD CONSTRAINT agent_generations_request_id_fkey FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE;


--
-- Name: agent_selections agent_selections_chosen_generation_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_selections
    ADD CONSTRAINT agent_selections_chosen_generation_id_fkey FOREIGN KEY (chosen_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE;


--
-- Name: agent_selections agent_selections_request_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.agent_selections
    ADD CONSTRAINT agent_selections_request_id_fkey FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE;


--
-- Name: preference_pairs preference_pairs_chosen_generation_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.preference_pairs
    ADD CONSTRAINT preference_pairs_chosen_generation_id_fkey FOREIGN KEY (chosen_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE;


--
-- Name: preference_pairs preference_pairs_rejected_generation_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.preference_pairs
    ADD CONSTRAINT preference_pairs_rejected_generation_id_fkey FOREIGN KEY (rejected_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE;


--
-- Name: preference_pairs preference_pairs_request_id_fkey; Type: FK CONSTRAINT; Schema: growpath_legacy; Owner: -
--

ALTER TABLE ONLY growpath_legacy.preference_pairs
    ADD CONSTRAINT preference_pairs_request_id_fkey FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE;


--
-- Name: chunks chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: knowledge; Owner: -
--

ALTER TABLE ONLY knowledge.chunks
    ADD CONSTRAINT chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES knowledge.documents(document_id);


--
-- Name: assessment_questions assessment_question_round_scope; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_questions
    ADD CONSTRAINT assessment_question_round_scope FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES public.diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE;


--
-- Name: assessment_questions assessment_questions_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_questions
    ADD CONSTRAINT assessment_questions_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;


--
-- Name: assessment_questions assessment_questions_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_questions
    ADD CONSTRAINT assessment_questions_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id);


--
-- Name: growth_reports assessment_reports_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_reports
    ADD CONSTRAINT assessment_reports_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;


--
-- Name: assessment_responses assessment_responses_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_responses
    ADD CONSTRAINT assessment_responses_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;


--
-- Name: book_skills book_skill_map_isbn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.book_skills
    ADD CONSTRAINT book_skill_map_isbn_fkey FOREIGN KEY (isbn) REFERENCES public.books(isbn) ON DELETE CASCADE;


--
-- Name: book_skills book_skill_map_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.book_skills
    ADD CONSTRAINT book_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;


--
-- Name: certification_skills cert_skill_map_cert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certification_skills
    ADD CONSTRAINT cert_skill_map_cert_id_fkey FOREIGN KEY (cert_id) REFERENCES public.certifications(cert_id) ON DELETE CASCADE;


--
-- Name: certification_skills cert_skill_map_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certification_skills
    ADD CONSTRAINT cert_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;


--
-- Name: course_skills course_skill_map_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_skills
    ADD CONSTRAINT course_skill_map_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(course_id) ON DELETE CASCADE;


--
-- Name: course_skills course_skill_map_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_skills
    ADD CONSTRAINT course_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;


--
-- Name: departments departments_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);


--
-- Name: departments departments_parent_department_id_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_parent_department_id_institution_id_fkey FOREIGN KEY (parent_department_id, institution_id) REFERENCES public.departments(department_id, institution_id);


--
-- Name: diagnostic_rounds diagnostic_rounds_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_rounds
    ADD CONSTRAINT diagnostic_rounds_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;


--
-- Name: employee_certifications employee_certifications_certification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_certifications
    ADD CONSTRAINT employee_certifications_certification_id_fkey FOREIGN KEY (certification_id) REFERENCES public.certifications(cert_id);


--
-- Name: employee_certifications employee_certifications_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_certifications
    ADD CONSTRAINT employee_certifications_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;


--
-- Name: employee_education_records employee_education_records_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_education_records
    ADD CONSTRAINT employee_education_records_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;


--
-- Name: employee_education_records employee_education_records_major_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_education_records
    ADD CONSTRAINT employee_education_records_major_id_fkey FOREIGN KEY (major_id) REFERENCES public.majors(major_id);


--
-- Name: employee_input_profiles employee_input_profiles_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_input_profiles
    ADD CONSTRAINT employee_input_profiles_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;


--
-- Name: employee_recommended_prompts employee_recommended_prompts_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_recommended_prompts
    ADD CONSTRAINT employee_recommended_prompts_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;


--
-- Name: employee_skills employee_skills_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_skills
    ADD CONSTRAINT employee_skills_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;


--
-- Name: employee_skills employee_skills_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_skills
    ADD CONSTRAINT employee_skills_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id);


--
-- Name: employees employees_department_scope; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_department_scope FOREIGN KEY (department_id, institution_id) REFERENCES public.departments(department_id, institution_id);


--
-- Name: employees employees_grade_scope; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_grade_scope FOREIGN KEY (job_grade_id, institution_id) REFERENCES public.job_grades(job_grade_id, institution_id);


--
-- Name: employees employees_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);


--
-- Name: assessment_responses fk_response_question_scope; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_responses
    ADD CONSTRAINT fk_response_question_scope FOREIGN KEY (question_id, project_id, assessment_type) REFERENCES public.assessment_questions(question_id, project_id, assessment_type) ON DELETE CASCADE;


--
-- Name: growth_reports growth_roadmap_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_reports
    ADD CONSTRAINT growth_roadmap_fk FOREIGN KEY (roadmap_id) REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE;


--
-- Name: growth_reports growth_same_project_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_reports
    ADD CONSTRAINT growth_same_project_fk FOREIGN KEY (roadmap_id, project_id) REFERENCES public.roadmaps(roadmap_id, project_id) ON DELETE CASCADE;


--
-- Name: job_grades job_grades_institution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_grades
    ADD CONSTRAINT job_grades_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);


--
-- Name: job_skills job_skill_map_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_skills
    ADD CONSTRAINT job_skill_map_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE CASCADE;


--
-- Name: job_skills job_skill_map_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_skills
    ADD CONSTRAINT job_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;


--
-- Name: learning_resource_embeddings learning_resource_embeddings_certification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embeddings_certification_id_fkey FOREIGN KEY (certification_id) REFERENCES public.certifications(cert_id) ON DELETE CASCADE;


--
-- Name: learning_resource_embeddings learning_resource_embeddings_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embeddings_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(course_id) ON DELETE CASCADE;


--
-- Name: learning_resource_embeddings learning_resource_embeddings_isbn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embeddings_isbn_fkey FOREIGN KEY (isbn) REFERENCES public.books(isbn) ON DELETE CASCADE;


--
-- Name: learning_resource_embeddings learning_resource_embeddings_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embeddings_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE CASCADE;


--
-- Name: learning_resource_embeddings learning_resource_embeddings_major_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embeddings_major_id_fkey FOREIGN KEY (major_id) REFERENCES public.majors(major_id) ON DELETE CASCADE;


--
-- Name: learning_resource_embeddings learning_resource_embeddings_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.learning_resource_embeddings
    ADD CONSTRAINT learning_resource_embeddings_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;


--
-- Name: major_skills major_skill_map_major_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.major_skills
    ADD CONSTRAINT major_skill_map_major_id_fkey FOREIGN KEY (major_id) REFERENCES public.majors(major_id) ON DELETE CASCADE;


--
-- Name: major_skills major_skill_map_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.major_skills
    ADD CONSTRAINT major_skill_map_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE;


--
-- Name: projects projects_draft_prompt_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_draft_prompt_version_id_fkey FOREIGN KEY (draft_prompt_version_id) REFERENCES public.prompt_versions(prompt_version_id);


--
-- Name: projects projects_plan_prompt_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_plan_prompt_version_id_fkey FOREIGN KEY (plan_prompt_version_id) REFERENCES public.prompt_versions(prompt_version_id);


--
-- Name: prompt_versions prompt_versions_parent_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prompt_versions
    ADD CONSTRAINT prompt_versions_parent_version_id_fkey FOREIGN KEY (parent_version_id) REFERENCES public.prompt_versions(prompt_version_id);


--
-- Name: roadmap_comments roadmap_comments_author_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_comments
    ADD CONSTRAINT roadmap_comments_author_employee_id_fkey FOREIGN KEY (author_employee_id) REFERENCES public.employees(employee_id);


--
-- Name: roadmap_comments roadmap_comments_roadmap_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_comments
    ADD CONSTRAINT roadmap_comments_roadmap_id_fkey FOREIGN KEY (roadmap_id) REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE;


--
-- Name: roadmaps roadmap_generations_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT roadmap_generations_session_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(project_id) ON DELETE CASCADE;


--
-- Name: roadmaps roadmap_round_scope; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT roadmap_round_scope FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES public.diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE;


--
-- Name: projects roadmap_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT roadmap_sessions_user_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id) ON DELETE CASCADE;


--
-- Name: roadmap_step_resources roadmap_step_resources_certification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_certification_id_fkey FOREIGN KEY (certification_id) REFERENCES public.certifications(cert_id);


--
-- Name: roadmap_step_resources roadmap_step_resources_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(course_id);


--
-- Name: roadmap_step_resources roadmap_step_resources_isbn_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_isbn_fkey FOREIGN KEY (isbn) REFERENCES public.books(isbn);


--
-- Name: roadmap_step_resources roadmap_step_resources_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_step_resources
    ADD CONSTRAINT roadmap_step_resources_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.roadmap_steps(step_id) ON DELETE CASCADE;


--
-- Name: roadmap_steps roadmap_steps_roadmap_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmap_steps
    ADD CONSTRAINT roadmap_steps_roadmap_id_fkey FOREIGN KEY (roadmap_id) REFERENCES public.roadmaps(roadmap_id) ON DELETE CASCADE;


--
-- Name: roadmaps roadmaps_prompt_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roadmaps
    ADD CONSTRAINT roadmaps_prompt_version_id_fkey FOREIGN KEY (prompt_version_id) REFERENCES public.prompt_versions(prompt_version_id);


--
-- Name: employees users_target_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT users_target_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE SET NULL;


--
-- Name: evaluation_item_definitions evaluation_item_definition_parent_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_item_definitions
    ADD CONSTRAINT evaluation_item_definition_parent_fk FOREIGN KEY (parent_item_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id);


--
-- Name: evaluation_item_definitions evaluation_item_definition_schema_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_item_definitions
    ADD CONSTRAINT evaluation_item_definition_schema_fk FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id);


--
-- Name: evaluation_item_definitions evaluation_item_definition_skill_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_item_definitions
    ADD CONSTRAINT evaluation_item_definition_skill_fk FOREIGN KEY (skill_id) REFERENCES public.skill_tags(skill_id);


--
-- Name: evaluation_result_schemas evaluation_result_schema_institution_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_result_schemas
    ADD CONSTRAINT evaluation_result_schema_institution_fk FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);


--
-- Name: evaluation_schema_sources evaluation_schema_source_id_schema_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_schema_sources
    ADD CONSTRAINT evaluation_schema_source_id_schema_fk FOREIGN KEY (evaluation_item_definition_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id);


--
-- Name: evaluation_schema_sources evaluation_schema_source_node_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_schema_sources
    ADD CONSTRAINT evaluation_schema_source_node_fk FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: evaluation_schema_sources evaluation_schema_source_schema_fk; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.evaluation_schema_sources
    ADD CONSTRAINT evaluation_schema_source_schema_fk FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id);


--
-- Name: rag_chunk_embeddings rag_chunk_embedding_rag_chunk_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunk_embeddings
    ADD CONSTRAINT rag_chunk_embedding_rag_chunk_id_fkey FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id) ON DELETE CASCADE;


--
-- Name: rag_chunks rag_chunk_regulation_version_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunks
    ADD CONSTRAINT rag_chunk_regulation_version_id_fkey FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);


--
-- Name: rag_chunk_sources rag_chunk_source_rag_chunk_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunk_sources
    ADD CONSTRAINT rag_chunk_source_rag_chunk_id_fkey FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id);


--
-- Name: rag_chunk_sources rag_chunk_source_regulation_node_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.rag_chunk_sources
    ADD CONSTRAINT rag_chunk_source_regulation_node_id_fkey FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: regulation_files regulation_file_regulation_version_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_files
    ADD CONSTRAINT regulation_file_regulation_version_id_fkey FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);


--
-- Name: regulation_files regulation_file_source_file_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_files
    ADD CONSTRAINT regulation_file_source_file_id_fkey FOREIGN KEY (source_file_id) REFERENCES regulations.regulation_files(regulation_file_id);


--
-- Name: regulations regulation_institution_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulations
    ADD CONSTRAINT regulation_institution_id_fkey FOREIGN KEY (institution_id) REFERENCES public.institutions(institution_id);


--
-- Name: regulation_nodes regulation_node_parent_node_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_nodes
    ADD CONSTRAINT regulation_node_parent_node_id_fkey FOREIGN KEY (parent_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: regulation_nodes regulation_node_regulation_file_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_nodes
    ADD CONSTRAINT regulation_node_regulation_file_id_fkey FOREIGN KEY (regulation_file_id) REFERENCES regulations.regulation_files(regulation_file_id);


--
-- Name: regulation_nodes regulation_node_regulation_version_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_nodes
    ADD CONSTRAINT regulation_node_regulation_version_id_fkey FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);


--
-- Name: regulation_references regulation_reference_regulation_node_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_references
    ADD CONSTRAINT regulation_reference_regulation_node_id_fkey FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: regulation_references regulation_reference_target_node_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_references
    ADD CONSTRAINT regulation_reference_target_node_id_fkey FOREIGN KEY (target_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: regulation_references regulation_reference_target_regulation_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_references
    ADD CONSTRAINT regulation_reference_target_regulation_id_fkey FOREIGN KEY (target_regulation_id) REFERENCES regulations.regulations(regulation_id);


--
-- Name: regulation_references regulation_reference_target_version_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_references
    ADD CONSTRAINT regulation_reference_target_version_id_fkey FOREIGN KEY (target_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);


--
-- Name: regulation_scopes regulation_scope_applies_to_node_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_scopes
    ADD CONSTRAINT regulation_scope_applies_to_node_id_fkey FOREIGN KEY (applies_to_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: regulation_scopes regulation_scope_regulation_node_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_scopes
    ADD CONSTRAINT regulation_scope_regulation_node_id_fkey FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id);


--
-- Name: regulation_versions regulation_version_previous_version_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_versions
    ADD CONSTRAINT regulation_version_previous_version_id_fkey FOREIGN KEY (previous_version_id) REFERENCES regulations.regulation_versions(regulation_version_id);


--
-- Name: regulation_versions regulation_version_regulation_id_fkey; Type: FK CONSTRAINT; Schema: regulations; Owner: -
--

ALTER TABLE ONLY regulations.regulation_versions
    ADD CONSTRAINT regulation_version_regulation_id_fkey FOREIGN KEY (regulation_id) REFERENCES regulations.regulations(regulation_id);


--
-- Name: agent_generations; Type: ROW SECURITY; Schema: growpath_legacy; Owner: -
--

ALTER TABLE growpath_legacy.agent_generations ENABLE ROW LEVEL SECURITY;

--
-- Name: agent_selections; Type: ROW SECURITY; Schema: growpath_legacy; Owner: -
--

ALTER TABLE growpath_legacy.agent_selections ENABLE ROW LEVEL SECURITY;

--
-- Name: finetuning_datasets; Type: ROW SECURITY; Schema: growpath_legacy; Owner: -
--

ALTER TABLE growpath_legacy.finetuning_datasets ENABLE ROW LEVEL SECURITY;

--
-- Name: preference_pairs; Type: ROW SECURITY; Schema: growpath_legacy; Owner: -
--

ALTER TABLE growpath_legacy.preference_pairs ENABLE ROW LEVEL SECURITY;

--
-- Name: roadmap_requests; Type: ROW SECURITY; Schema: growpath_legacy; Owner: -
--

ALTER TABLE growpath_legacy.roadmap_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: test_mock_profiles; Type: ROW SECURITY; Schema: growpath_legacy; Owner: -
--

ALTER TABLE growpath_legacy.test_mock_profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: catalog_api_sources; Type: ROW SECURITY; Schema: growpath_meta; Owner: -
--

ALTER TABLE growpath_meta.catalog_api_sources ENABLE ROW LEVEL SECURITY;

--
-- Name: schema_migrations; Type: ROW SECURITY; Schema: growpath_meta; Owner: -
--

ALTER TABLE growpath_meta.schema_migrations ENABLE ROW LEVEL SECURITY;

--
-- Name: chunks; Type: ROW SECURITY; Schema: knowledge; Owner: -
--

ALTER TABLE knowledge.chunks ENABLE ROW LEVEL SECURITY;

--
-- Name: documents; Type: ROW SECURITY; Schema: knowledge; Owner: -
--

ALTER TABLE knowledge.documents ENABLE ROW LEVEL SECURITY;

--
-- Name: assessment_questions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assessment_questions ENABLE ROW LEVEL SECURITY;

--
-- Name: assessment_responses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assessment_responses ENABLE ROW LEVEL SECURITY;

--
-- Name: book_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.book_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: books; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.books ENABLE ROW LEVEL SECURITY;

--
-- Name: certification_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.certification_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: certifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.certifications ENABLE ROW LEVEL SECURITY;

--
-- Name: course_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.course_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: courses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;

--
-- Name: departments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;

--
-- Name: diagnostic_rounds; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.diagnostic_rounds ENABLE ROW LEVEL SECURITY;

--
-- Name: employee_certifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employee_certifications ENABLE ROW LEVEL SECURITY;

--
-- Name: employee_education_records; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employee_education_records ENABLE ROW LEVEL SECURITY;

--
-- Name: employee_input_profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employee_input_profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: employee_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employee_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: employees; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;

--
-- Name: growth_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.growth_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: institutions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.institutions ENABLE ROW LEVEL SECURITY;

--
-- Name: job_grades; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_grades ENABLE ROW LEVEL SECURITY;

--
-- Name: job_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: learning_resource_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.learning_resource_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: major_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.major_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: majors; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.majors ENABLE ROW LEVEL SECURITY;

--
-- Name: projects; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

--
-- Name: prompt_versions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.prompt_versions ENABLE ROW LEVEL SECURITY;

--
-- Name: roadmap_comments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.roadmap_comments ENABLE ROW LEVEL SECURITY;

--
-- Name: roadmap_step_resources; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.roadmap_step_resources ENABLE ROW LEVEL SECURITY;

--
-- Name: roadmap_steps; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.roadmap_steps ENABLE ROW LEVEL SECURITY;

--
-- Name: roadmaps; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.roadmaps ENABLE ROW LEVEL SECURITY;

--
-- Name: skill_tags; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.skill_tags ENABLE ROW LEVEL SECURITY;

--
-- Name: evaluation_item_definitions; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.evaluation_item_definitions ENABLE ROW LEVEL SECURITY;

--
-- Name: evaluation_result_schemas; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.evaluation_result_schemas ENABLE ROW LEVEL SECURITY;

--
-- Name: evaluation_schema_sources; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.evaluation_schema_sources ENABLE ROW LEVEL SECURITY;

--
-- Name: rag_chunk_embeddings; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.rag_chunk_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: rag_chunk_sources; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.rag_chunk_sources ENABLE ROW LEVEL SECURITY;

--
-- Name: rag_chunks; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.rag_chunks ENABLE ROW LEVEL SECURITY;

--
-- Name: regulation_files; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.regulation_files ENABLE ROW LEVEL SECURITY;

--
-- Name: regulation_nodes; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.regulation_nodes ENABLE ROW LEVEL SECURITY;

--
-- Name: regulation_references; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.regulation_references ENABLE ROW LEVEL SECURITY;

--
-- Name: regulation_scopes; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.regulation_scopes ENABLE ROW LEVEL SECURITY;

--
-- Name: regulation_versions; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.regulation_versions ENABLE ROW LEVEL SECURITY;

--
-- Name: regulations; Type: ROW SECURITY; Schema: regulations; Owner: -
--

ALTER TABLE regulations.regulations ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict 3tkaCs03LOEj7jFQz4ObFINgTYcVGV6czuGjz43SRDJZxfZGsAclBOIowU34wS7
