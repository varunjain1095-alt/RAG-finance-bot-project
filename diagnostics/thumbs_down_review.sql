-- Full turn context for recent thumbs-down feedback.
-- Params: start_date, end_date, limit (default 25)

SELECT
    f.feedback_id,
    f.rating,
    f.comment,
    f.created_at AS feedback_at,
    ql.turn_id,
    ql.session_id,
    ql.experience_level,
    ql.user_question,
    ql.final_answer,
    ql.refusal_category,
    ql.retrieved_chunks,
    ql.citation_flow,
    ql.latency_input_filters_ms,
    ql.latency_embedding_ms,
    ql.latency_retrieval_ms,
    ql.latency_rerank_ms,
    ql.latency_generation_ms,
    ql.latency_postprocessing_ms,
    ql.latency_total_ms,
    ql.cost_usd
FROM feedback f
JOIN query_logs ql ON ql.turn_id = f.turn_id
WHERE f.rating = 'thumbs_down'
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY f.created_at DESC
LIMIT %(limit)s;
