# Diagnostic SQL queries

Pre-built, parameterized queries against `query_logs`, `feedback`, and related tables.

## CLI

```bash
set PYTHONPATH=src
python scripts/diag.py list
python scripts/diag.py thumbs_down_review --days 14
python scripts/diag.py operational_health_summary
python scripts/operational_health_report.py --days 7
```

Default window: last 7 days (`start_date` / `end_date`).

## Query index

| Query | Purpose |
|-------|---------|
| `retrieval/thin_retrieval_refusals` | Grounding / thin retrieval refusals |
| `retrieval/cited_not_top_parent` | Cited URL not from rank-1 retrieved parent |
| `retrieval/thumbs_down_retrieval_context` | Thumbs-down with retrieval payload |
| `retrieval/top1_rerank_score_distribution` | Score buckets for threshold tuning |
| `reranking/top1_after_rerank` | Post-rerank top parent inspection |
| `reranking/parent_dedup_collisions` | Fewer than 3 parents after dedup |
| `reranking/rerank_latency_outliers` | Slow rerank calls (`--min-latency-ms`) |
| `generation/regeneration_by_citation` | Citation-driven regenerations |
| `generation/structured_fallback_answers` | Fallback refusals after failed citation |
| `generation/raw_vs_final_divergence` | Large raw vs final answer deltas |
| `citation/invented_url_failures` | URL provenance failures (high severity) |
| `citation/citation_outcome_breakdown` | Outcome / failure_mode counts |
| `citation/same_question_different_citations` | Citation inconsistency detector |
| `thumbs_down_review` | Full turn context for negative feedback |
| `aggregate_thumbs_down_by_failure_mode` | Stage classification rollup |
| `operational_health_summary` | Single-row health metrics |

## Metabase

See `METABASE_SETUP.md` for Docker service, read-only connection, and recommended panels.
