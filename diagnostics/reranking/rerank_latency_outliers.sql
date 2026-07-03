-- Rerank latency outliers (p95 investigation).
-- Params: start_date, end_date, min_latency_ms (default 600)

SELECT
    ql.turn_id,
    ql.created_at,
    ql.latency_rerank_ms,
    ql.latency_retrieval_ms,
    ql.latency_total_ms,
    ql.user_question
FROM query_logs ql
WHERE ql.latency_rerank_ms >= %(min_latency_ms)s
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.latency_rerank_ms DESC
LIMIT 100;
