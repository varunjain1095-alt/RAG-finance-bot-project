-- Thumbs-down turns where retrieval may have failed (empty or low-score chunks).
-- Params: start_date, end_date

SELECT
    f.feedback_id,
    f.rating,
    f.comment,
    ql.turn_id,
    ql.user_question,
    ql.final_answer,
    jsonb_array_length(ql.retrieved_chunks) AS retrieved_count,
    ql.retrieved_chunks
FROM feedback f
JOIN query_logs ql ON ql.turn_id = f.turn_id
WHERE f.rating = 'thumbs_down'
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC;
