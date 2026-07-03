-- Phase 4: session turn embedding indexes and FKs (table created in 002_embedding_768.sql)

CREATE INDEX IF NOT EXISTS idx_session_turn_embeddings_session_id
    ON session_turn_embeddings(session_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_turn_embeddings_query_log_id
    ON session_turn_embeddings(query_log_id)
    WHERE query_log_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_session_turn_embeddings_embedding_hnsw
    ON session_turn_embeddings USING hnsw (embedding vector_cosine_ops);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_session_turn_embeddings_session'
    ) THEN
        ALTER TABLE session_turn_embeddings
            ADD CONSTRAINT fk_session_turn_embeddings_session
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_session_turn_embeddings_query_log'
    ) THEN
        ALTER TABLE session_turn_embeddings
            ADD CONSTRAINT fk_session_turn_embeddings_query_log
            FOREIGN KEY (query_log_id) REFERENCES query_logs(turn_id) ON DELETE CASCADE;
    END IF;
END $$;
