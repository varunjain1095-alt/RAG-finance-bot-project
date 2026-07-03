-- Distribution of top retrieved rerank scores (for threshold tuning).
-- Params: start_date, end_date

SELECT
    width_bucket(
        (ql.retrieved_chunks->0->>'rerank_score')::float,
        0.0, 1.0, 10
    ) AS score_bucket,
    COUNT(*) AS turn_count,
    MIN((ql.retrieved_chunks->0->>'rerank_score')::float) AS bucket_min,
    MAX((ql.retrieved_chunks->0->>'rerank_score')::float) AS bucket_max
FROM query_logs ql
WHERE ql.refusal_category IS NULL
  AND jsonb_array_length(ql.retrieved_chunks) > 0
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
GROUP BY score_bucket
ORDER BY score_bucket;
