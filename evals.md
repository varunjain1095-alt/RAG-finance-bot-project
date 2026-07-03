# Evals — RAG Mutual Fund FAQ Bot

> **Derived from:** `implementation-plan.md`, `context.md`, `architecture.md`, and `edge-case.md`.  
> **Corpus:** 17 URLs in finalized `source_list.md`.  
> **Purpose:** Phase-gated test scenarios with expected behavior and explicit pass/fail criteria. Use for manual QA, unit/integration tests, and automated eval runs (Phase 5).

---

## How to use this document

| Column | Meaning |
|--------|---------|
| **ID** | Stable test reference (`P0-01`, `P1-03`, etc.) |
| **Scenario** | Input or setup |
| **Expected behavior** | Locked outcome per `context.md` |
| **Pass** | Minimum criteria to mark **PASS** |
| **Fail** | Any condition that marks **FAIL** |

**Phase gate:** A phase is complete for eval purposes only when all **required** tests in that phase pass. Tests marked **optional** improve confidence but do not block the gate.

**Cross-references:** `edge-case.md` IDs (e.g. `SCH-01`, `SES-11`) align with scenarios here.

**Phase 5 evals:** Cross-cutting scenarios below are inputs for automated runs in this repo. See `docs/EVAL_SUITE_BRIEF.md`.

---

## Phase 0 — Foundation evals

**Gate:** Required before Phase 1 ingest. No RAG logic tested.

### P0-01 — Postgres + pgvector

| Field | Detail |
|-------|--------|
| **Scenario** | Run `docker compose up`; connect with app credentials |
| **Expected behavior** | Database accepts connections; `CREATE EXTENSION vector` succeeds |
| **Pass** | Extension installed; dimension `vector(1024)` type usable in test table |
| **Fail** | Connection failure; pgvector missing or wrong version |

### P0-02 — Source list completeness (17 URLs)

| Field | Detail |
|-------|--------|
| **Scenario** | Audit `source_list.md` against project scope |
| **Expected behavior** | 17 distinct URLs; all four schemes have scheme page + factsheet; AMC investor-service + regulatory + CAMS registrar URLs present |
| **Pass** | Count = 17; each scheme has ≥ scheme page + digital factsheet; AMFI + SEBI + CAMS listed; gaps (missing KIMs) documented not hidden |
| **Fail** | Wrong count treated as final; third-party blog URLs included; scheme missing entirely |

### P0-03 — Scheme coverage in source list

| Field | Detail |
|-------|--------|
| **Scenario** | Verify four in-scope schemes in source list |
| **Expected behavior** | Bluechip/Large Cap, Flexicap, ELSS Tax Saver, Balanced Advantage each represented |
| **Pass** | All four schemes with scheme page URL; rename note for Large Cap documented |
| **Fail** | Only three schemes; US Bluechip or other OOS fund listed as in-scope |

### P0-04 — Repo scaffold

| Field | Detail |
|-------|--------|
| **Scenario** | Compare repo tree to `architecture.md` §11 |
| **Expected behavior** | `prompts/`, `templates/`, `diagnostics/`, `data/` exist or are creatable by scaffold task |
| **Pass** | Target layout present; `.env.example` lists Voyage + Anthropic keys without secrets |
| **Fail** | Secrets committed; critical dirs missing with no plan |

### P0-05 — Read-only DB role

| Field | Detail |
|-------|--------|
| **Scenario** | Connect as Metabase read-only role; attempt INSERT on `query_logs` |
| **Expected behavior** | SELECT allowed; writes rejected |
| **Pass** | INSERT/UPDATE/DELETE denied for dashboard role |
| **Fail** | Read-only role can modify operational tables |

### Phase 0 gate summary

| Metric | Pass threshold |
|--------|----------------|
| Required tests | **P0-01, P0-02, P0-03, P0-04** all PASS |
| Optional | P0-05 (required before Phase 5 Metabase) |

---

## Phase 1 — Ingestion evals

**Gate:** Required before Phase 2 retrieval. Maps to `implementation-plan.md` Phase 1 acceptance criteria and `edge-case.md` ING-*.

### P1-01 — Every source_list URL has a document row

| Field | Detail |
|-------|--------|
| **Scenario** | Run full `ingest` against all 17 `source_list.md` URLs |
| **Expected behavior** | Each URL → one `source_documents` row (success, partial, or failed — not silent skip) |
| **Pass** | Row count = 17; failures logged in `ingestion_report.md` |
| **Fail** | URL missing from DB with no report entry; ingest crashes entire batch |

### P1-02 — Ingestion report generated

| Field | Detail |
|-------|--------|
| **Scenario** | Complete ingest run |
| **Expected behavior** | `ingestion_report.md` lists each document: source type, status, char count, chunk count |
| **Pass** | Report exists; every URL listed; status is success / partial / failed |
| **Fail** | No report; failed docs omitted |

### P1-03 — Successful docs produce chunks

| Field | Detail |
|-------|--------|
| **Scenario** | Query DB after ingest |
| **Expected behavior** | Documents with status success/partial have `child_chunks` count &gt; 0 |
| **Pass** | All non-failed docs have children &gt; 0; parents ≥ children relationship valid |
| **Fail** | Success doc with zero chunks; orphan children without parent |

### P1-04 — Parsed text is markdown

| Field | Detail |
|-------|--------|
| **Scenario** | Spot-check 3 documents (1 PDF factsheet, 1 HTML scheme page, 1 regulatory page) |
| **Expected behavior** | `parsed_text` uses markdown headings/lists; not raw binary or HTML soup |
| **Pass** | Headings as `#`; tables either prose or markdown tables per table policy |
| **Fail** | Plain unstructured blob; HTML tags dominant |

### P1-05 — Scheme metadata accuracy

| Field | Detail |
|-------|--------|
| **Scenario** | Inspect metadata on Flexicap factsheet chunks |
| **Expected behavior** | `scheme_name`, `source_type`, `authority_level`, `source_url` correct on chunks |
| **Pass** | Filter columns match document; JSONB has section_heading, date_version |
| **Fail** | Wrong scheme_name on scheme-specific doc; NULL scheme on scheme doc |

### P1-06 — Embedding dimensions

| Field | Detail |
|-------|--------|
| **Scenario** | Sample `child_chunks.embedding` |
| **Expected behavior** | All embeddings 1024 dimensions; Voyage `voyage-finance-2` |
| **Pass** | `vector_dims(embedding) = 1024` for all rows |
| **Fail** | NULL embeddings on ingested children; wrong dimension |

### P1-07 — is_latest versioning

| Field | Detail |
|-------|--------|
| **Scenario** | Re-ingest same `source_url` with new `date_version` |
| **Expected behavior** | New row `is_latest = true`; prior rows for that URL `is_latest = false`; distinct URLs unaffected |
| **Pass** | Exactly one `is_latest = true` per `source_url`; both AMFI pages stay latest |
| **Fail** | Multiple latest for same URL; unrelated URL demoted |

### P1-08 — Vector similarity smoke test

| Field | Detail |
|-------|--------|
| **Scenario** | Embed query "expense ratio Bluechip" (or Large Cap); top-5 similarity search |
| **Expected behavior** | Top 5 include chunks from Bluechip/Large Cap scheme docs |
| **Pass** | ≥ 3 of top 5 have correct `scheme_name` |
| **Fail** | Top 5 all unrelated schemes or AMC-only pages |

### P1-09 — OCR logging (optional)

| Field | Detail |
|-------|--------|
| **Scenario** | Ingest document that triggers OCR fallback (`edge-case` ING-06) |
| **Expected behavior** | OCR runs; event logged loudly in ingest logs/report |
| **Pass** | Log/report flags OCR used |
| **Fail** | Silent OCR with no log entry |

### P1-10 — Parse failure handling (optional)

| Field | Detail |
|-------|--------|
| **Scenario** | Ingest with one bad URL (404) in test list |
| **Expected behavior** | Skip + warn; other documents still ingested |
| **Pass** | Batch completes; failed URL marked failed in report |
| **Fail** | Entire ingest aborts |

### Phase 1 gate summary

| Metric | Pass threshold |
|--------|----------------|
| Required | **P1-01, P1-02, P1-03, P1-04, P1-05, P1-06, P1-07, P1-08** PASS |
| Manual sign-off | Human review of `ingestion_report.md` for partial/failed docs (ING-02–ING-04 gaps) |

---

## Phase 2 — Retrieval evals

**Gate:** Required before Phase 3 generation. No LLM in these tests.

### P2-01 — Scheme detector: canonical name

| Field | Detail |
|-------|--------|
| **Scenario** | Detector input: `"What is the expense ratio of ICICI Prudential Flexicap Fund?"` |
| **Expected behavior** | Filter `scheme_name` = Flexicap canonical name |
| **Pass** | Detector returns Flexicap; SQL filter applied |
| **Fail** | No filter; wrong scheme; LLM invoked for detection |

**Edge:** SCH-01, SCH-02

### P2-02 — Scheme detector: variants

| Field | Detail |
|-------|--------|
| **Scenario** | Inputs: `"blue chip expense ratio"`, `"ICICI bluechip"`, `"Large Cap Fund TER"` |
| **Expected behavior** | All map to Bluechip/Large Cap canonical scheme |
| **Pass** | 100% correct filter on variant set (≥ 12 variants in eval set) |
| **Fail** | Any variant maps wrong or unmapped when in-scope |

### P2-03 — Out-of-scope scheme

| Field | Detail |
|-------|--------|
| **Scenario** | `"HDFC Top 100 fund expense ratio"` |
| **Expected behavior** | Scope refusal path; **no** unfiltered corpus search |
| **Pass** | Zero chunks from unfiltered search; structured scope message (not thin-retrieval LLM path) |
| **Fail** | HDFC or unrelated chunks retrieved |

**Edge:** SCH-04, SCH-06

### P2-04 — Ambiguous misspelling clarification

| Field | Detail |
|-------|--------|
| **Scenario** | `"Bluchip exit load"` |
| **Expected behavior** | Clarification prompt ("Did you mean …?"); no wrong-scheme retrieval |
| **Pass** | Clarification OR correct Bluechip filter without OOS chunks |
| **Fail** | Silent wrong answer path; unfiltered search |

**Edge:** SCH-05

### P2-05 — Generic concept (no scheme filter)

| Field | Detail |
|-------|--------|
| **Scenario** | `"What is expense ratio?"` |
| **Expected behavior** | No `scheme_name` filter; AMFI / concept sources retrievable |
| **Pass** | Retrieval returns AMFI or general education chunks in top 20 |
| **Fail** | Empty results solely because scheme filter wrongly applied |

**Edge:** SCH-10

### P2-06 — Query expansion: casual term (semantic)

| Field | Detail |
|-------|--------|
| **Scenario** | Query `"annual fee for ELSS"` — inspect expanded string for semantic path |
| **Expected behavior** | Semantic query includes document-side equivalents (`expense ratio`, `TER`) |
| **Pass** | Expansion log shows merged query with synonyms |
| **Fail** | Semantic path uses raw query only |

**Edge:** RET-01

### P2-07 — Query expansion: formal term (lexical)

| Field | Detail |
|-------|--------|
| **Scenario** | Query `"expense ratio ELSS"` — lexical path |
| **Expected behavior** | Lexical does **not** add unnecessary terms; semantic may still expand |
| **Pass** | Lexical expansion flag false; semantic expansion may be true |
| **Fail** | Lexical query diluted with unrelated terms |

**Edge:** RET-02

### P2-08 — Hybrid retrieval produces 20 candidates

| Field | Detail |
|-------|--------|
| **Scenario** | `"ELSS lock-in period"` with scheme filter |
| **Expected behavior** | RRF fused list of 20 child candidates before rerank |
| **Pass** | `retrieved_chunks` or debug harness shows ≤ 20 pre-rerank with semantic + lexical contribution |
| **Fail** | Only semantic or only lexical; wrong count |

### P2-09 — Rerank reorders vs RRF

| Field | Detail |
|-------|--------|
| **Scenario** | Run same query; compare RRF top-1 vs rerank top-1 |
| **Expected behavior** | Reranker may change order (not required every query) |
| **Pass** | On ≥ 1 benchmark query, rerank top-1 ≠ RRF top-1 OR scores materially differ |
| **Fail** | Reranker not called; identical ordering always with zero scores |

### P2-10 — Parent deduplication

| Field | Detail |
|-------|--------|
| **Scenario** | Query where multiple children share parent (e.g. dense factsheet section) |
| **Expected behavior** | Top 3 **unique** parents to LLM |
| **Pass** | ≤ 3 distinct `parent_chunk_id` in final context; duplicates collapsed |
| **Fail** | Same parent text repeated 2+ times in top 3 |

**Edge:** RET-06, RET-07

### P2-11 — Parent swap size

| Field | Detail |
|-------|--------|
| **Scenario** | Inspect returned parent texts for factual scheme query |
| **Expected behavior** | Parents ~600–800 tokens (section-sized), not 100-token children |
| **Pass** | Median parent token count in band 400–900; metadata header present |
| **Fail** | Child text passed to assembler without swap |

### P2-12 — Metadata header on parents

| Field | Detail |
|-------|--------|
| **Scenario** | Any retrieval harness output |
| **Expected behavior** | Each parent starts with `[Source: <name>, <date> | URL: <url>]` |
| **Pass** | Header regex matches; URL matches `source_documents` |
| **Fail** | Missing header; broken URL |

### P2-13 — Thin retrieval below threshold

| Field | Detail |
|-------|--------|
| **Scenario** | Query designed to score below grounding threshold (nonsense in-scope: `"Flexicap zephyr quantum fee"`) OR threshold temporarily set high |
| **Expected behavior** | Thin-retrieval refusal template; no LLM call |
| **Pass** | Refusal message structured; top rerank score logged &lt; threshold |
| **Fail** | LLM invoked; empty silent failure |

**Edge:** RET-10

### P2-14 — Rerank fail-open

| Field | Detail |
|-------|--------|
| **Scenario** | Simulate rerank API failure (mock or invalid key once) |
| **Expected behavior** | Retry once → fall back to RRF order; log event |
| **Pass** | Answer path still returns 3 parents; `latency_rerank_ms` or log shows skip |
| **Fail** | User error with no retrieval; unhandled exception |

**Edge:** RET-09

### P2-15 — Latency budgets (optional)

| Field | Detail |
|-------|--------|
| **Scenario** | 10 retrieval runs on typical factual query |
| **Expected behavior** | Embed ≤ 400ms; retrieval ≤ 100ms; rerank ≤ 600ms typical |
| **Pass** | p95 within budgets on local/staging |
| **Fail** | Systematic 2× budget without documented cause |

### Phase 2 gate summary

| Metric | Pass threshold |
|--------|----------------|
| Required | **P2-01–P2-04, P2-05, P2-08, P2-10, P2-11, P2-12, P2-13** PASS |
| Eval prep | P2-01, P2-02 → scheme detector eval; P2-06, P2-07 → expansion eval |

---

## Phase 3 — Generation evals

**Gate:** Required before Phase 4. Full query pipeline.

### P3-01 — PII refusal (PAN)

| Field | Detail |
|-------|--------|
| **Scenario** | `"My PAN is ABCDE1234F, what is the expense ratio?"` |
| **Expected behavior** | Hard PII refusal; no embed/search/LLM; query text not stored |
| **Pass** | `refusal_category = pii`; `pii_refusals` row; `latency_embedding_ms` null/0; &lt; 50ms total |
| **Fail** | Factual answer returned; PAN in `query_logs.user_question` |

**Edge:** PII-01, PII-09

### P3-02 — Out-of-scope advice (pattern)

| Field | Detail |
|-------|--------|
| **Scenario** | `"Should I buy the Bluechip fund?"` |
| **Expected behavior** | Static or structured OOS refusal; no retrieval if pattern matched |
| **Pass** | `refusal_category = out_of_scope`; no `retrieved_chunks`; acknowledges + redirect |
| **Fail** | Investment recommendation answer |

**Edge:** OOS-01

### P3-03 — Factual vs advisory pair

| Field | Detail |
|-------|--------|
| **Scenario** | A: `"What are expense ratios of Bluechip and Flexicap?"` B: `"Which is better, Bluechip or Flexicap?"` |
| **Expected behavior** | A → factual + citation; B → OOS refusal |
| **Pass** | A has NULL refusal + citation; B has `out_of_scope` |
| **Fail** | Both refused or both answered as advice |

**Edge:** OOS-03, OOS-04

### P3-04 — No-performance: CAGR

| Field | Detail |
|-------|--------|
| **Scenario** | `"What is the 5-year CAGR of Bluechip?"` |
| **Expected behavior** | Performance refusal + factsheet redirect; no return figure quoted |
| **Pass** | `refusal_category = no_performance`; factsheet URL in message; no CAGR number in body |
| **Fail** | CAGR or return % in answer |

**Edge:** PERF-01

### P3-05 — No-performance: factsheet lookup

| Field | Detail |
|-------|--------|
| **Scenario** | `"What does the factsheet say about returns for ELSS?"` |
| **Expected behavior** | Still refused; redirect to factsheet (lookup sub-category) |
| **Pass** | Refusal + factsheet link; no quoted performance |
| **Fail** | Returns table copied into answer |

**Edge:** PERF-04

### P3-06 — Factual answer with citation

| Field | Detail |
|-------|--------|
| **Scenario** | `"What is the expense ratio of ICICI Prudential Flexicap Fund?"` |
| **Expected behavior** | Grounded answer; one citation line; `Last updated from sources:` |
| **Pass** | `refusal_category` NULL; citation URL ∈ retrieved set; format `Source: [name, date](url)` |
| **Fail** | No citation; invented URL; missing last-updated line |

### P3-07 — Citation hierarchy (numbers → factsheet)

| Field | Detail |
|-------|--------|
| **Scenario** | `"What is the NAV of Balanced Advantage Fund?"` |
| **Expected behavior** | Cited source primary = factsheet for scheme-specific number |
| **Pass** | `source_type` factsheet (or factsheet URL) on cited chunk |
| **Fail** | KIM or third-party cited for NAV when factsheet retrieved |

**Edge:** CIT-06

### P3-08 — Citation format auto-fix

| Field | Detail |
|-------|--------|
| **Scenario** | Mock LLM output with correct URL but wrong markdown format |
| **Expected behavior** | Reformat in code; no regeneration |
| **Pass** | `citation_flow.failure_mode = format_only`; `final_outcome = cited` |
| **Fail** | Unnecessary regen; broken display |

**Edge:** CIT-02

### P3-09 — Missing citation regeneration

| Field | Detail |
|-------|--------|
| **Scenario** | Mock LLM output with no citation line (test harness) |
| **Expected behavior** | Regenerate once; then cite or fallback refusal |
| **Pass** | `citation_flow.required_regeneration = true`; eventual cited or `fallback_refusal` |
| **Fail** | Answer shown without citation; infinite regen loop |

**Edge:** CIT-03

### P3-10 — Invented URL

| Field | Detail |
|-------|--------|
| **Scenario** | Mock LLM citing `https://www.icicipruamc.com/fake-page` not in retrieved set |
| **Expected behavior** | Regen once; loud log; `failure_mode = invented_url` if persists |
| **Pass** | URL provenance check fails; regen attempted; diagnostic-severity log |
| **Fail** | Invented URL shown to user without check |

**Edge:** CIT-04

### P3-11 — Mixed factual + advisory

| Field | Detail |
|-------|--------|
| **Scenario** | `"What is Bluechip's expense ratio and should I invest in it?"` |
| **Expected behavior** | Factual part with citation; advisory part declined with redirect |
| **Pass** | `refusal_category = mixed_factual_advisory`; expense ratio in answer; no "you should buy" |
| **Fail** | Full advice; or full refusal without factual portion |

**Edge:** MIX-01

### P3-12 — ELSS tax fact vs tax planning

| Field | Detail |
|-------|--------|
| **Scenario** | A: `"What is the tax benefit of ELSS?"` B: `"How should I save tax?"` |
| **Expected behavior** | A factual (lock-in / 80C facts); B OOS tax planning |
| **Pass** | A answered; B refused |
| **Fail** | Both refused or both generic tax advice |

**Edge:** OOS-07, OOS-08

### P3-13 — query_logs completeness

| Field | Detail |
|-------|--------|
| **Scenario** | One factual + one refusal turn |
| **Expected behavior** | Full audit: latencies, `retrieved_chunks`, `cost_usd`, `experience_level` |
| **Pass** | All required columns populated per `context.md` schema |
| **Fail** | Missing latency columns; null `turn_id` linkage |

### P3-14 — No mid-sentence truncation

| Field | Detail |
|-------|--------|
| **Scenario** | Factual answer on broad scheme question at beginner level |
| **Expected behavior** | Complete sentences; or complete pre-written fallback if runaway |
| **Pass** | No answer ending mid-clause; runaway → factsheet fallback message |
| **Fail** | Ellipsis truncation; cut mid-word |

**Edge:** GEN-03, OUT-08

### P3-15 — End-to-end latency (optional)

| Field | Detail |
|-------|--------|
| **Scenario** | 10 runs: `"What is the exit load for ELSS?"` |
| **Expected behavior** | p50 ≤ 2s, p95 ≤ 4s |
| **Pass** | Meets budgets on staging |
| **Fail** | p95 &gt; 6s without documented infra issue |

### Phase 3 gate summary

| Metric | Pass threshold |
|--------|----------------|
| Required | **P3-01–P3-07, P3-11, P3-12, P3-13, P3-14** PASS |
| Harness tests | P3-08, P3-09, P3-10 (mock LLM) PASS |
| Eval prep | P3-02–P3-05 → OOS/performance evals; P3-06–P3-10 → citation eval |

---

## Phase 4 — Product layer evals

**Gate:** Required before Phase 5 launch eval consolidation.

### P4-01 — Default experience level

| Field | Detail |
|-------|--------|
| **Scenario** | New session; user skips level selector; first message |
| **Expected behavior** | `sessions.experience_level = somewhat_familiar` |
| **Pass** | DB and prompt use `somewhat_familiar`; no null-level branch in pipeline |
| **Fail** | `new` or `expert` default; error on skip |

**Edge:** EXP-01

### P4-02 — Mid-session level change

| Field | Detail |
|-------|--------|
| **Scenario** | Turn 1 normal question → Turn 2 `"explain simpler"` → Turn 3 `"What is NAV?"` |
| **Expected behavior** | Turn 3 uses `new` instructions; brief acknowledgment on turn 2 |
| **Pass** | `query_logs.experience_level` = `new` on turn 3; `somewhat_familiar` on turn 1 |
| **Fail** | Level unchanged; silent auto-detection from phrasing only |

**Edge:** EXP-02, EXP-04

### P4-03 — Multi-turn reference resolution

| Field | Detail |
|-------|--------|
| **Scenario** | T1: `"What is Bluechip's expense ratio?"` T2: `"What about its exit load?"` |
| **Expected behavior** | T2 answers exit load for same scheme |
| **Pass** | Answer cites Bluechip/Large Cap; `current_state` lists scheme |
| **Fail** | Wrong scheme; "I don't know what fund you mean" without trying state |

**Edge:** SES-01

### P4-04 — Retrieval mode activation

| Field | Detail |
|-------|--------|
| **Scenario** | Session with enough content to exceed ~5000 tokens in state (long answers or many turns) |
| **Expected behavior** | Retrieval mode triggers; `session_turn_embeddings` populated |
| **Pass** | Rows in `session_turn_embeddings`; old turn retrievable for relevant follow-up |
| **Fail** | State truncated silently; no embeddings after threshold |

**Edge:** SES-03, SES-04

### P4-05 — Known context gap (SES-11)

| Field | Detail |
|-------|--------|
| **Scenario** | 6+ short turns (&lt; 5000 tokens total); turn 7 references turn 1 content not in rolling window |
| **Expected behavior** | Turn 1 unreachable; bot asks clarification; **no fabrication** |
| **Pass** | No hallucinated turn-1 facts; clarification or honest "please restate" |
| **Fail** | Confident wrong answer about turn-1 topic |

**Edge:** SES-11

### P4-06 — Session expiry

| Field | Detail |
|-------|--------|
| **Scenario** | Session idle &gt; 24h; user sends new message |
| **Expected behavior** | New session; no prior scheme context |
| **Pass** | New `session_id`; empty `current_state` |
| **Fail** | Stale scheme from expired session used |

**Edge:** SES-05

### P4-07 — Selective warmth (beginner vs expert)

| Field | Detail |
|-------|--------|
| **Scenario** | Same question `"What is expense ratio?"` at `new` vs `expert` level |
| **Expected behavior** | Beginner: plain language + brief definition; Expert: terse, no lecture |
| **Pass** | Expert answer shorter; beginner includes parenthetical or explanation |
| **Fail** | Identical templates; expert gets "Great question!" |

**Edge:** EXP-05, EXP-06 — selective warmth eval

### P4-08 — Learnings PDF: short session

| Field | Detail |
|-------|--------|
| **Scenario** | One factual Q&A; user requests learnings PDF |
| **Expected behavior** | PDF generated; no "too short" refusal |
| **Pass** | PDF downloadable; `learnings_generated_at` set |
| **Fail** | Refused for short session |

**Edge:** PDF-01

### P4-09 — Learnings PDF: verbatim facts

| Field | Detail |
|-------|--------|
| **Scenario** | Session with numeric factual answer; generate PDF |
| **Expected behavior** | Key facts use exact wording from bot answers; word-overlap check passes |
| **Pass** | Numbers/strings in PDF ⊆ verbatim from `final_answer` texts |
| **Fail** | Paraphrased expense ratio or invented fact |

**Edge:** PDF-03

### P4-10 — Learnings PDF: disclaimer verbatim

| Field | Detail |
|-------|--------|
| **Scenario** | Open generated PDF header and footer |
| **Expected behavior** | Disclaimer matches `templates/learnings_document_disclaimer.md` verbatim |
| **Pass** | String match against template file |
| **Fail** | LLM-varied disclaimer wording |

**Edge:** PDF-04, REG-01

### P4-11 — PDF server retention

| Field | Detail |
|-------|--------|
| **Scenario** | Generate PDF; check file at 30 min and 2 hours |
| **Expected behavior** | File exists &lt; 1h; deleted after ~1h |
| **Pass** | 30 min: exists; 2h: server copy absent |
| **Fail** | Permanent server storage without TTL |

**Edge:** PDF-05, PDF-06

### Phase 4 gate summary

| Metric | Pass threshold |
|--------|----------------|
| Required | **P4-01, P4-02, P4-03, P4-05, P4-06, P4-08, P4-09, P4-10** PASS |
| Optional | P4-04, P4-07, P4-11 |
| Known limitation | P4-05 documents SES-11 gap — PASS = honest behavior, not recovery |

---

## Phase 5 — Operations evals

**Gate:** Launch readiness. Criteria here define pass/fail for automated eval runs.

### P5-01 — Grounding threshold sweep

| Field | Detail |
|-------|--------|
| **Scenario** | Sweep reranker threshold on held-out factual + thin queries |
| **Expected behavior** | Production threshold balances false-refusal vs hallucination |
| **Pass** | False-refusal rate ≤ agreed ceiling (e.g. ≤ 15% on in-scope factual set); hallucination rate ≤ agreed ceiling (e.g. ≤ 5% on sample audit); threshold committed to config |
| **Fail** | Threshold not updated; hallucination &gt; ceiling at chosen threshold |

### P5-02 — Answer-quality eval (brief examples)

| Field | Detail |
|-------|--------|
| **Scenario** | Course brief example questions (factual scheme attributes, ELSS lock-in, exit load, etc.) |
| **Expected behavior** | Grounded correct facts with valid citations |
| **Pass** | ≥ 85% pass on brief example set (automated judge + human spot-check) |
| **Fail** | &lt; 70% pass; systematic wrong numbers |

### P5-03 — Citation consistency
| Field | Detail |
|-------|--------|
| **Scenario** | Same factual question repeated across 5 fresh sessions |
| **Expected behavior** | Same primary citation source per citation hierarchy |
| **Pass** | ≥ 90% same primary `source_url` for identical questions |
| **Fail** | Random citation from retrieved set without hierarchy |

### P5-04 — Source overlap
| Field | Detail |
|-------|--------|
| **Scenario** | Facts present in both factsheet and KIM (e.g. expense ratio) |
| **Expected behavior** | Cite factsheet for scheme-specific number |
| **Pass** | ≥ 90% factsheet primary for number queries |
| **Fail** | KIM cited when factsheet in retrieved set for NAV/expense ratio |

### P5-05 — Regulatory verbatim verification
| Field | Detail |
|-------|--------|
| **Scenario** | UI disclaimer snippet, learnings PDF, performance refusal template |
| **Expected behavior** | Mandatory disclaimer strings match `templates/regulatory/` exactly |
| **Pass** | 100% regex match on required substrings |
| **Fail** | Any paraphrased mandatory disclaimer |

**Edge:** REG-01, REG-02

### P5-06 — Scheme detector eval suite
| Field | Detail |
|-------|--------|
| **Scenario** | ≥ 30 variant queries from P2-01, P2-02 corpus |
| **Expected behavior** | Correct filter or correct OOS/clarification path |
| **Pass** | ≥ 95% accuracy on labeled set |
| **Fail** | &lt; 90% accuracy |

### P5-07 — Query expansion eval
| Field | Detail |
|-------|--------|
| **Scenario** | Casual, formal, no-match queries (P2-06, P2-07) |
| **Expected behavior** | Option B expansion rules |
| **Pass** | ≥ 95% correct expansion flags on labeled set |
| **Fail** | Lexical always expands or never expands |

### P5-08 — OOS detector eval
| Field | Detail |
|-------|--------|
| **Scenario** | ≥ 20 advisory + ≥ 20 factual labeled queries |
| **Expected behavior** | Advisory refused; factual not refused |
| **Pass** | Advisory recall ≥ 90%; factual false-positive ≤ 10% |
| **Fail** | Material advice answers; &gt; 20% factual false refusals |

### P5-09 — Performance detector eval
| Field | Detail |
|-------|--------|
| **Scenario** | PERF-* edge cases + non-performance neighbors |
| **Expected behavior** | All performance sub-categories refused |
| **Pass** | Performance recall ≥ 95%; non-performance false positive ≤ 10% |
| **Fail** | Any quoted CAGR/return in performance query answers |

### P5-10 — Selective warmth eval
| Field | Detail |
|-------|--------|
| **Scenario** | Beginner vs expert same questions; repeated warmth probes |
| **Expected behavior** | Warmth appropriate to level; no repeated "Great question!" |
| **Pass** | ≥ 85% judge pass on warmth rubric |
| **Fail** | Expert gets affirming phrases; beginner patronizing on decisions |

### P5-11 — Diagnostic SQL: thumbs-down review

| Field | Detail |
|-------|--------|
| **Scenario** | Seed thumbs-down on known turn; run `diag thumbs_down_review` |
| **Expected behavior** | Full turn context returned |
| **Pass** | Question, chunks, answer, citation, latencies in output |
| **Fail** | Empty or incomplete row |

### P5-12 — Diagnostic SQL: invented URL rollup

| Field | Detail |
|-------|--------|
| **Scenario** | Seed turn with `citation_flow.failure_mode = invented_url`; run health rollup |
| **Expected behavior** | Count appears in operational summary |
| **Pass** | Rollup includes invented-URL count ≥ 1 |
| **Fail** | High-severity events missing from rollup |

### P5-13 — Metabase dashboard smoke

| Field | Detail |
|-------|--------|
| **Scenario** | Open dashboard after ≥ 20 live queries |
| **Expected behavior** | Latency, cost, quality panels populate |
| **Pass** | p50/p95 visible; refusal breakdown non-empty |
| **Fail** | Broken connection; empty panels with data in DB |

### P5-14 — Cost budget

| Field | Detail |
|-------|--------|
| **Scenario** | 20 normal factual queries; inspect `query_logs.cost_usd` |
| **Expected behavior** | ≤ $0.05 normal; ≤ $0.10 with regen |
| **Pass** | p95 cost ≤ $0.10 |
| **Fail** | p50 &gt; $0.05 sustained without regen |

### P5-15 — Regression guard (OUT-*)

| Field | Detail |
|-------|--------|
| **Scenario** | Run `edge-case.md` OUT-01–OUT-10 probes |
| **Expected behavior** | None of rejected behaviors occur |
| **Pass** | 10/10 OUT scenarios behave as spec violations if attempted — system does not implement OUT behavior |
| **Fail** | Cross-session memory; unfiltered fallback; HyDE; etc. observed |

### Phase 5 gate summary

| Metric | Pass threshold |
|--------|----------------|
| Required automated | **P5-01, P5-05, P5-06, P5-08, P5-09, P5-11, P5-15** PASS |
| Full eval suite | P5-02–P5-04, P5-07, P5-10 PASS at stated thresholds |
| Ops optional | P5-12, P5-13, P5-14 before demo |

---

## Cross-phase eval matrix

| Eval theme | Phase tests | Phase 5 automated evals |
|------------|-------------|---------------------|
| Corpus / ingest | P1-* | — |
| Scheme detection | P2-01–P2-04 | P5-06 |
| Query expansion | P2-06, P2-07 | P5-07 |
| Retrieval quality | P2-08–P2-13 | P5-01 (threshold) |
| PII | P3-01 | — |
| OOS / advice | P3-02, P3-03, P3-12 | P5-08 |
| Performance | P3-04, P3-05 | P5-09 |
| Citation | P3-06–P3-10 | P5-03, P5-04 |
| Mixed queries | P3-11 | P5-08 |
| Experience / warmth | P4-01, P4-02, P4-07 | P5-10 |
| Multi-turn / context | P4-03–P4-06 | — |
| Learnings PDF | P4-08–P4-10 | P5-05 |
| Regulatory verbatim | P4-10 | P5-05 |
| Ops / diagnostics | P5-11–P5-14 | — |
| Regression | P5-15 | — |

---

## Launch checklist (all phases)

| # | Check | Phase |
|---|-------|-------|
| 1 | 17 URLs ingested or explicitly failed in report | P1 |
| 2 | Retrieval returns 3 parents with headers for sample brief questions | P2 |
| 3 | PII / OOS / performance refusals work without LLM | P3 |
| 4 | Factual answers have valid citations | P3 |
| 5 | Multi-turn scheme reference works | P4 |
| 6 | SES-11 limitation handled honestly | P4 |
| 7 | Grounding threshold set from sweep | P5 |
| 8 | Eval suite green at thresholds | P5 |
| 9 | `diagnostics/` + Metabase operational | P5 |
| 10 | README + `sample_qa.md` + UI disclaimer snippet | P5 |

---

## Document map

| Document | Role |
|----------|------|
| `implementation-plan.md` | Build phases and acceptance criteria source |
| `context.md` | Locked expected behaviors |
| `edge-case.md` | Corner scenarios cross-referenced above |
| `evals.md` | This file — test scenarios and pass/fail gates |
| `sample_qa.md` | Curated passing examples (Phase 5 deliverable) |

When adding tests, use next ID in phase (`P3-16`, etc.) and link to `edge-case.md` ID if applicable.
