-- Same question text with different cited URLs across sessions.
-- Params: start_date, end_date

SELECT
    ql.user_question,
    COUNT(DISTINCT ql.citation_flow->>'cited_url') AS distinct_citations,
    COUNT(*) AS turn_count
FROM query_logs ql
WHERE ql.citation_flow->>'cited_url' IS NOT NULL
  AND ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s
GROUP BY ql.user_question
HAVING COUNT(DISTINCT ql.citation_flow->>'cited_url') > 1
ORDER BY turn_count DESC
LIMIT 50;
