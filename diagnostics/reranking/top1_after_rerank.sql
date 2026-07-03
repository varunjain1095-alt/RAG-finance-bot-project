-- Rerank changed ordering: pre-rerank top child != post-rerank top parent URL.
-- Params: start_date, end_date

SELECT
    ql.turn_id,
    ql.created_at,
    ql.user_question,
    ql.retrieved_chunks->0 AS top_after_rerank,
    ql.latency_rerank_ms
FROM query_logs ql
WHERE ql.refusal_category IS NULL
  AND jsonb_array_length(ql.retrieved_chunks) > 0
  AND ql.latency_rerank_ms > 0
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC
LIMIT 200;
