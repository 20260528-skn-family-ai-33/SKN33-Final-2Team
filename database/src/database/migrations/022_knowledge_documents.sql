-- Non-regulation evidence. Existing regulations.* and HR data are untouched.
SET LOCAL lock_timeout = '10s';
SET LOCAL search_path TO public, extensions;
CREATE SCHEMA IF NOT EXISTS knowledge;
REVOKE ALL ON SCHEMA knowledge FROM PUBLIC;

CREATE TABLE knowledge.documents (
    document_id text PRIMARY KEY,
    category text NOT NULL CHECK (category IN ('수자원공사 정보','사내 생활안내')),
    title text NOT NULL CHECK (length(title)>0),
    document_kind text NOT NULL CHECK (document_kind IN ('report','plan','web_page','guide')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX knowledge_document_category_idx ON knowledge.documents(category);

CREATE TABLE knowledge.chunks (
    chunk_id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES knowledge.documents(document_id),
    display_order integer NOT NULL CHECK (display_order>0),
    chunk_text text NOT NULL CHECK (length(chunk_text)>0),
    chunk_text_sha256 text NOT NULL CHECK (chunk_text_sha256 ~ '^[0-9a-f]{64}$'),
    is_virtual boolean NOT NULL,
    metadata jsonb NOT NULL CHECK (jsonb_typeof(metadata)='object'),
    embedding_model text,
    dimensions integer,
    input_sha256 text,
    embedding vector(1536),
    embedded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(document_id,display_order),
    CHECK (chunk_text_sha256=encode(sha256(convert_to(chunk_text,'UTF8')),'hex')),
    CHECK ((embedding IS NULL AND embedding_model IS NULL AND dimensions IS NULL
            AND input_sha256 IS NULL AND embedded_at IS NULL)
        OR (embedding IS NOT NULL AND embedding_model IS NOT NULL AND dimensions IS NOT NULL
            AND input_sha256 IS NOT NULL AND embedded_at IS NOT NULL
            AND embedding_model='text-embedding-3-small' AND dimensions=1536
            AND vector_norm(embedding)>0 AND input_sha256=chunk_text_sha256))
);
COMMENT ON TABLE knowledge.documents IS 'Company information and synthetic workplace guides; category is required by the search API.';
COMMENT ON TABLE knowledge.chunks IS 'Verbatim supplied chunks and original provenance. is_virtual must accompany retrieval results.';
ALTER TABLE knowledge.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge.chunks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA knowledge FROM PUBLIC;
DO $access$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON SCHEMA knowledge FROM anon;
        REVOKE ALL ON ALL TABLES IN SCHEMA knowledge FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON SCHEMA knowledge FROM authenticated;
        REVOKE ALL ON ALL TABLES IN SCHEMA knowledge FROM authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
        GRANT USAGE ON SCHEMA knowledge TO service_role;
        GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA knowledge TO service_role;
    END IF;
END $access$;
NOTIFY pgrst, 'reload schema';
