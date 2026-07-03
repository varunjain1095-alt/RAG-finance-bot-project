-- Classify thumbs-down turns by likely failure stage.
-- Params: start_date, end_date

SELECT
    CASE
        WHEN ql.refusal_category = 'thin_retrieval' THEN 'retrieval'
        WHEN (ql.citation_flow->>'url_provenance_passed')::boolean IS FALSE THEN 'citation'
        WHEN (ql.citation_flow->>'required_regeneration')::boolean IS TRUE THEN 'generation_citation'
        WHEN ql.latency_rerank_ms > 600 THEN 'rerank_latency'
        WHEN jsonb_array_length(ql.retrieved_chunks) = 0 THEN 'retrieval_empty'
        ELSE 'generation_other'
    END AS failure_stage,
    COUNT(*) AS thumbs_down_count
FROM feedback f
JOIN query_logs ql ON ql.turn_id = f.turn_id
WHERE f.rating = 'thumbs_down'
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
GROUP BY failure_stage
ORDER BY thumbs_down_count DESC;
