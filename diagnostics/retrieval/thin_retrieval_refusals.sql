-- Thin retrieval refusals: turns where bot refused due to low grounding.
-- Params: start_date, end_date (timestamptz)

SELECT
    ql.turn_id,
    ql.session_id,
    ql.created_at,
    ql.user_question,
    ql.refusal_category,
    ql.latency_retrieval_ms,
    ql.latency_rerank_ms,
    (ql.retrieved_chunks->0->>'rerank_score')::float AS top_rerank_score,
    jsonb_array_length(ql.retrieved_chunks) AS retrieved_parent_count
FROM query_logs ql
WHERE ql.refusal_category = 'thin_retrieval'
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC;
