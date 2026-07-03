-- Phase 1 corpus tables (source_documents, parent_chunks, child_chunks)

CREATE TABLE IF NOT EXISTS source_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    date_version TEXT NOT NULL,
    is_latest BOOLEAN NOT NULL DEFAULT TRUE,
    scheme_name TEXT NULL,
    authority_level TEXT NOT NULL,
    parsed_text TEXT NOT NULL DEFAULT '',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES source_documents(document_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    scheme_name TEXT NULL,
    source_type TEXT NOT NULL,
    authority_level TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS child_chunks (
    child_chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_chunk_id UUID NOT NULL REFERENCES parent_chunks(parent_chunk_id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES source_documents(document_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(768) NULL,
    scheme_name TEXT NULL,
    source_type TEXT NOT NULL,
    authority_level TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

CREATE INDEX IF NOT EXISTS idx_child_chunks_scheme_name ON child_chunks(scheme_name);
CREATE INDEX IF NOT EXISTS idx_child_chunks_source_type ON child_chunks(source_type);
CREATE INDEX IF NOT EXISTS idx_child_chunks_authority_level ON child_chunks(authority_level);
CREATE INDEX IF NOT EXISTS idx_child_chunks_document_id ON child_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_search_tsv ON child_chunks USING GIN(search_tsv);

CREATE INDEX IF NOT EXISTS idx_child_chunks_embedding_hnsw
    ON child_chunks USING hnsw (embedding vector_cosine_ops);
