-- Structured fallback answers (citation failed after regen or runaway).
-- Params: start_date, end_date

SELECT
    ql.turn_id,
    ql.created_at,
    ql.user_question,
    ql.citation_flow->>'final_outcome' AS final_outcome,
    ql.final_answer
FROM query_logs ql
WHERE ql.citation_flow->>'final_outcome' IN (
    'fallback_refusal', 'runaway_fallback'
)
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC;
