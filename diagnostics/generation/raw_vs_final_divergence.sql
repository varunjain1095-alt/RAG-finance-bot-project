-- Turns where post-processing changed output substantially (raw vs final length delta).
-- Params: start_date, end_date, min_delta_chars (default 80)

SELECT
    ql.turn_id,
    ql.created_at,
    ql.user_question,
    LENGTH(ql.raw_llm_output) AS raw_len,
    LENGTH(ql.final_answer) AS final_len,
    ABS(LENGTH(ql.raw_llm_output) - LENGTH(ql.final_answer)) AS delta_len
FROM query_logs ql
WHERE ql.raw_llm_output IS NOT NULL
  AND ABS(LENGTH(ql.raw_llm_output) - LENGTH(ql.final_answer)) >= %(min_delta_chars)s
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY delta_len DESC
LIMIT 100;
