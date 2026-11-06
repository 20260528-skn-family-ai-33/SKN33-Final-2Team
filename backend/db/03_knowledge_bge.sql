-- #125: 원문과 기존 OpenAI 1536차원 벡터를 보존하는 별도 BGE-M3 색인.
SET LOCAL lock_timeout = '10s';
CREATE SCHEMA IF NOT EXISTS app_ext;
CREATE TABLE IF NOT EXISTS app_ext.knowledge_chunk_vectors (
    chunk_id text NOT NULL REFERENCES knowledge.chunks(chunk_id) ON DELETE CASCADE,
    embedding_model text NOT NULL CHECK (embedding_model = 'BAAI/bge-m3'),
    dimensions integer NOT NULL CHECK (dimensions = 1024),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    embedding vector(1024) NOT NULL CHECK (vector_norm(embedding) > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, embedding_model)
);
ALTER TABLE app_ext.knowledge_chunk_vectors ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON app_ext.knowledge_chunk_vectors FROM PUBLIC;
DO $access$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT USAGE ON SCHEMA app_ext TO service_role;
        GRANT SELECT,INSERT,UPDATE,DELETE ON app_ext.knowledge_chunk_vectors TO service_role;
    END IF;
END $access$;
