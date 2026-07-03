# Metabase setup (Phase 5)

Local-only operational dashboard connecting to Postgres via the read-only role.

## 1. Start services

```bash
docker compose up -d postgres metabase
```

- Postgres: `localhost:5433`
- Metabase UI: http://localhost:3000

## 2. First-time Metabase setup

1. Create admin account (local only).
2. Add database:
   - Type: PostgreSQL
   - Host: `host.docker.internal` (Docker Desktop) or `postgres` if Metabase uses compose network
   - Port: `5432` (internal) or `5433` from host
   - Database: `rag_bot`
   - User: `metabase_readonly`
   - Password: `metabase_readonly` (change in production)

## 3. Import diagnostic queries

Copy SQL from `diagnostics/**/*.sql` into Metabase **Saved questions**. Use Metabase variables:

| SQL param | Metabase variable type |
|-----------|------------------------|
| `start_date` | Field filter / Date |
| `end_date` | Date |
| `min_latency_ms` | Number (default 600) |
| `min_delta_chars` | Number (default 80) |
| `limit` | Number (default 25) |

Suggested saved question names match CLI paths (e.g. `thumbs_down_review`).

## 4. Recommended dashboard panels (~8)

1. **Latency overview** — from `operational_health_summary` or custom: p50/p95 `latency_total_ms` by day
2. **Cost trend** — `SUM(cost_usd)` by day from `query_logs`
3. **Quality summary** — refusal counts by `refusal_category`; regeneration rate from `citation_flow`
4. **Invented URLs** — count from `citation/invented_url_failures`
5. **Thumbs-down rate** — `feedback` vs total turns
6. **Experience level mix** — `query_logs.experience_level` distribution
7. **Session signals** — `sessions.learnings_generated_at` count; avg turns per session
8. **Thumbs-down drill-down** — linked table from `thumbs_down_review`

Refresh: live queries on page load (no cache at project scale).

## 5. Security

- `metabase_readonly` role is SELECT-only (see `db/init/02_metabase_readonly.sql`).
- Do not expose Metabase publicly without authentication hardening.
