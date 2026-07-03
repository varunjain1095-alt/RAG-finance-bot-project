-- High-severity: cited URL not in retrieved chunk URL set.
-- Params: start_date, end_date

SELECT
    ql.turn_id,
    ql.session_id,
    ql.created_at,
    ql.user_question,
    ql.citation_flow->>'cited_url' AS cited_url,
    ql.citation_flow->>'url_provenance_passed' AS provenance_passed,
    ql.retrieved_chunks
FROM query_logs ql
WHERE (
    (ql.citation_flow->>'url_provenance_passed')::boolean IS FALSE
    OR ql.citation_flow->>'failure_mode' = 'invented_url'
)
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
ORDER BY ql.created_at DESC;
