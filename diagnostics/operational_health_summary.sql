-- Operational health rollup for scheduled review.
-- Params: start_date, end_date

SELECT
    COUNT(*) AS total_turns,
    COUNT(*) FILTER (WHERE refusal_category IS NOT NULL) AS refusal_turns,
    COUNT(*) FILTER (WHERE refusal_category = 'pii') AS pii_refusals,
    COUNT(*) FILTER (WHERE refusal_category = 'out_of_scope') AS oos_refusals,
    COUNT(*) FILTER (WHERE refusal_category = 'no_performance') AS performance_refusals,
    COUNT(*) FILTER (WHERE refusal_category = 'thin_retrieval') AS thin_retrieval_refusals,
    COUNT(*) FILTER (
        WHERE (ql.citation_flow->>'required_regeneration')::boolean IS TRUE
    ) AS citation_regenerations,
    COUNT(*) FILTER (
        WHERE ql.citation_flow->>'failure_mode' = 'invented_url'
    ) AS invented_url_count,
    COUNT(*) FILTER (WHERE f.rating = 'thumbs_down') AS thumbs_down_count,
    ROUND(AVG(ql.latency_total_ms)::numeric, 1) AS avg_latency_ms,
    ROUND(
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ql.latency_total_ms)::numeric,
        1
    ) AS p50_latency_ms,
    ROUND(
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ql.latency_total_ms)::numeric,
        1
    ) AS p95_latency_ms,
    ROUND(SUM(ql.cost_usd)::numeric, 4) AS total_cost_usd,
    ROUND(AVG(ql.cost_usd)::numeric, 6) AS avg_cost_usd
FROM query_logs ql
LEFT JOIN feedback f ON f.turn_id = ql.turn_id
WHERE ql.created_at >= %(start_date)s
  AND ql.created_at < %(end_date)s;
