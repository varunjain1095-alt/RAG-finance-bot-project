-- Phase 1b: local embeddings (BAAI/bge-base-en-v1.5, 768 dimensions)
-- Applied once via schema_migrations tracking (never re-run DELETE on re-ingest).

DROP INDEX IF EXISTS idx_child_chunks_embedding_hnsw;

DELETE FROM child_chunks;

ALTER TABLE child_chunks
    ALTER COLUMN embedding TYPE vector(768);

CREATE INDEX IF NOT EXISTS idx_child_chunks_embedding_hnsw
    ON child_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS session_turn_embeddings (
    turn_embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    query_log_id UUID NULL,
    turn_index INT NOT NULL,
    text TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
