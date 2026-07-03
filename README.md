# ICICI Prudential RAG Mutual Fund FAQ Bot

Factual Q&A bot for four in-scope ICICI Prudential mutual fund schemes. Locked architecture and scope are in `context.md`.

## Scope

- **AMC:** ICICI Prudential Asset Management Company
- **Schemes:** Large Cap (erstwhile Bluechip), Flexicap, ELSS Tax Saver, Balanced Advantage
- **Corpus:** 13 sources in `source_list.md` (factsheets, AMFI, SEBI, local FAQs + TER; CAMS as redirect fallback)
- **Out of scope:** Investment advice, performance claims, PII, cross-session memory, user name capture

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Python 3.11+
- API keys: Anthropic (Claude), Voyage AI (`voyage-finance-2`, `rerank-2`) — optional for retrieval rerank fail-open

## Quick start

1. **Configure environment**

   ```bash
   cp .env.example .env
   # Set ANTHROPIC_API_KEY, VOYAGE_API_KEY, DATABASE_URL (never commit .env)
   ```

2. **Start Postgres (+ optional Metabase)**

   ```bash
   docker compose up -d postgres
   docker compose up -d metabase   # optional — http://localhost:3000
   ```

3. **Install and migrate**

   ```bash
   pip install -r requirements.txt
   set PYTHONPATH=src
   python scripts/apply_migrations.py
   ```

4. **Ingest corpus (Phase 1)**

   ```bash
   python scripts/ingest.py
   # Review ingestion_report.md before production use
   ```

5. **Run API**

   ```bash
   uvicorn rag_bot.main:app --reload --app-dir src
   ```

   - Health: http://127.0.0.1:8000/health
   - Create session: `POST /session`
   - Chat: `POST /chat`
   - Learnings PDF: `GET /learnings/{session_id}`

6. **CLI alternatives**

   ```bash
   python scripts/ask.py "What is Flexicap expense ratio?"
   python scripts/retrieve.py "ELSS lock-in period"
   ```

See `sample_qa.md` for a grader demo script.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For `/chat` + learnings key-facts | Claude generation |
| `VOYAGE_API_KEY` | For rerank (embeddings use local BGE) | Rerank-2; fail-open to RRF if missing |
| `DATABASE_URL` | Yes | Default `postgresql://rag:rag@localhost:5433/rag_bot` |
| `ANTHROPIC_MODEL` | No | Default `claude-sonnet-4-6`; use `claude-haiku-4-5-20251001` for cheaper eval runs |
| `GROUNDING_THRESHOLD` | No | Default `0.35` — tune via Phase 5 threshold sweep |
| `SESSION_INACTIVITY_HOURS` | No | Default `24` |

## Database

- **Image:** `pgvector/pgvector:pg16` on host port **5433**
- **Init:** `vector` extension; `metabase_readonly` role (`metabase_readonly` / `metabase_readonly`)
- **Migrations:** `db/migrations/*.sql` via `scripts/apply_migrations.py`

## Operations (Phase 5)

### Diagnostic SQL

```bash
python scripts/diag.py list
python scripts/diag.py thumbs_down_review --days 14
python scripts/operational_health_report.py --days 7
```

Queries live in `diagnostics/` — see `diagnostics/README.md`.

### Session cleanup (cron)

```bash
python scripts/cleanup_expired_sessions.py
python scripts/cleanup_expired_sessions.py --dry-run
```

Clears `sessions.current_state` and `session_turn_embeddings` for sessions past 24h inactivity.

### Metabase

`docker compose up -d metabase` → http://localhost:3000. Setup: `diagnostics/METABASE_SETUP.md`.

### Evals

Run per `docs/EVAL_SUITE_BRIEF.md` and `evals.md`. Results in `evals/results/`.

## Latency and cost budgets

| Stage | Budget |
|-------|--------|
| End-to-end p50 | ≤ 2s |
| End-to-end p95 | ≤ 4s |
| Hard ceiling | 6s |
| Input filters | ≤ 50ms |
| Embedding | ≤ 400ms |
| Retrieval | ≤ 100ms |
| Rerank | ≤ 600ms |
| Generation (per LLM call) | ≤ 2.5s |
| Post-processing | ≤ 100ms |
| Cost per query (normal) | ≤ $0.05 |
| Cost per query (with regen) | ≤ $0.10 |

Logged per turn in `query_logs` (`latency_*_ms`, `cost_usd`). Review via `operational_health_summary` or Metabase.

## Added-complexity gate

Do **not** add pipeline layers (new retrieval stage, judge, verification pass) unless:

1. Eval data shows the current pipeline fails on a specific mode the layer would fix.
2. The layer's latency stays inside the per-stage budget above.
3. The layer's cost stays inside the per-query budget.
4. A simpler change (prompt tuning, threshold adjustment, dictionary update) would not produce the same lift.

Document evidence before merging architectural additions.

## Operational tuning (when budgets exceeded)

**Latency levers:** reduce hybrid candidates 20→10; switch to `rerank-2-lite`; lighter generation model; skip regeneration under stable citation audits; defer per-query citation alignment checks.

**Cost levers:** smaller model for auxiliary tasks; tighter prompts (fewer few-shots); batch where possible.

## Manual re-ingestion procedure

Factsheets and TER data update periodically. For this project scale, re-ingestion is **manual**:

1. Update URLs or files in `source_list.md` / `corpus/` if needed.
2. `docker compose up -d postgres`
3. `python scripts/apply_migrations.py`
4. `python scripts/ingest.py` (re-ingest changed sources; same-URL rows demote prior `is_latest` per URL only).
5. Review `ingestion_report.md` — resolve partial/failed parses before relying on answers.
6. Smoke test with `sample_qa.md` questions.

No automated cron for document change detection (deferred to production scope).

## Regulatory content review

Templates in `templates/regulatory/` and `templates/ui_disclaimer_snippet.md` were drafted for this build. **Annual review** (or on material SEBI/AMFI changes):

1. Verify mandatory disclaimers remain verbatim against official sources.
2. Confirm authoritative URLs are still official (sebi.gov.in, amfiindia.com, icicipruamc.com).
3. Re-run regulatory verbatim tests: `python -m unittest tests.test_regulatory_templates`

## Known limits

- Four ICICI Pru schemes only; no cross-AMC or US funds.
- Facts only — no performance figures, advice, or predictions.
- Session memory expires after 24h; no cross-session login.
- Corpus ~13 sources (not full 20-page brief); two digital factsheets may be partial — see `ingestion_report.md`.
- Embeddings: local BGE 768-dim (not Voyage 1024 in production corpus).
- Learnings PDF via fpdf2 (direct builder, not HTML→PDF).

## Project layout

| Path | Purpose |
|------|---------|
| `context.md` | Locked decisions (source of truth) |
| `source_list.md` | Corpus URLs |
| `prompts/` | System prompt + experience levels |
| `templates/` | Regulatory + learnings disclaimers |
| `diagnostics/` | SQL debug queries + Metabase guide |
| `evals.md` | Test scenarios |
| `docs/EVAL_SUITE_BRIEF.md` | Eval suite runbook (Phase 5) |
| `sample_qa.md` | Grader demo Q&A |
| `ingestion_report.md` | Parse/chunk report (post-ingest) |
| `src/rag_bot/` | Application code |

## Phase status

- [x] **Phase 0** — Foundation
- [x] **Phase 1** — Ingestion (see `ingestion_report.md`)
- [x] **Phase 2** — Retrieval
- [x] **Phase 3** — Generation
- [x] **Phase 4** — Product backend (session state, learnings PDF, experience levels)
- [x] **Phase 5** — Operations (diagnostics, Metabase scaffold, regulatory templates, README) — eval execution per `evals.md`

## Brief deliverables checklist

| Deliverable | Location |
|-------------|----------|
| Working prototype | API + CLI (`/chat`, `scripts/ask.py`) |
| Source list | `source_list.md` |
| README | This file |
| Sample Q&A | `sample_qa.md` |
| UI disclaimer snippet | `templates/ui_disclaimer_snippet.md` |
| Ingestion report | `ingestion_report.md` (after ingest) |
