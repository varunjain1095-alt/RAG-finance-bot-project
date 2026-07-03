-- Phase 3: sessions, query_logs, feedback, pii_refusals

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_identifier TEXT NULL,
    experience_level TEXT NOT NULL DEFAULT 'somewhat_familiar',
    current_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    learnings_generated_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_logs (
    turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    experience_level TEXT NOT NULL,
    user_question TEXT NOT NULL,
    retrieved_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_prompt TEXT NULL,
    raw_llm_output TEXT NULL,
    final_answer TEXT NOT NULL,
    cited_chunk_id UUID NULL,
    citation_flow JSONB NOT NULL DEFAULT '{}'::jsonb,
    refusal_category TEXT NULL,
    latency_input_filters_ms INT NOT NULL DEFAULT 0,
    latency_embedding_ms INT NOT NULL DEFAULT 0,
    latency_retrieval_ms INT NOT NULL DEFAULT 0,
    latency_rerank_ms INT NOT NULL DEFAULT 0,
    latency_generation_ms INT NOT NULL DEFAULT 0,
    latency_postprocessing_ms INT NOT NULL DEFAULT 0,
    latency_total_ms INT NOT NULL DEFAULT 0,
    cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_logs_session_id ON query_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_query_logs_created_at ON query_logs(created_at);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id UUID NOT NULL REFERENCES query_logs(turn_id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    rating TEXT NOT NULL CHECK (rating IN ('thumbs_up', 'thumbs_down')),
    comment TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (turn_id)
);

CREATE TABLE IF NOT EXISTS pii_refusals (
    pii_refusal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    pii_type TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pii_refusals_session_id ON pii_refusals(session_id);
