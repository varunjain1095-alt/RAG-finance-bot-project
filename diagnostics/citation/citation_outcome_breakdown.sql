-- Citation outcomes breakdown.
-- Params: start_date, end_date

SELECT
    ql.citation_flow->>'final_outcome' AS final_outcome,
    ql.citation_flow->>'failure_mode' AS failure_mode,
    COUNT(*) AS turn_count
FROM query_logs ql
WHERE ql.refusal_category IS NULL
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
GROUP BY 1, 2
ORDER BY turn_count DESC;
