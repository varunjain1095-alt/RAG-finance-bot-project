-- Sessions with multiple children mapping to same parent in retrieved set (dedup signal).
-- Params: start_date, end_date

SELECT
    ql.turn_id,
    ql.created_at,
    ql.user_question,
    ql.retrieved_chunks,
    jsonb_array_length(ql.retrieved_chunks) AS parent_slots
FROM query_logs ql
WHERE ql.refusal_category IS NULL
  AND jsonb_array_length(ql.retrieved_chunks) < 3
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC
LIMIT 200;
