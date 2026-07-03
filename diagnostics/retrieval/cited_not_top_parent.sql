-- Turns where cited URL exists but cited parent was not rank 1 in retrieved_chunks.
-- Params: start_date, end_date

SELECT
    ql.turn_id,
    ql.session_id,
    ql.created_at,
    ql.user_question,
    ql.citation_flow->>'cited_url' AS cited_url,
    ql.retrieved_chunks
FROM query_logs ql
WHERE ql.refusal_category IS NULL
  AND ql.citation_flow->>'cited_url' IS NOT NULL
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
  AND (
    ql.retrieved_chunks->0->>'source_url' IS DISTINCT FROM ql.citation_flow->>'cited_url'
  )
ORDER BY ql.created_at DESC;
