-- Regeneration triggered by citation enforcement.
-- Params: start_date, end_date

SELECT
    ql.turn_id,
    ql.created_at,
    ql.user_question,
    ql.citation_flow->>'required_regeneration' AS required_regeneration,
    ql.citation_flow->>'failure_mode' AS failure_mode,
    ql.citation_flow->>'final_outcome' AS final_outcome,
    ql.latency_generation_ms
FROM query_logs ql
WHERE (ql.citation_flow->>'required_regeneration')::boolean IS TRUE
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC;
