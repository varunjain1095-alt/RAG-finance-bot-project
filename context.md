# Project Context — RAG Mutual Fund FAQ Bot

> **Source:** `rag_bot_feature_inventory (1).md` — locked feature inventory and architectural decisions for the ICICI Prudential RAG FAQ bot. This file is the single reference for scope, locked decisions, and deferred items when building or reviewing the project.

---

# RAG Mutual Fund FAQ Bot — Feature Inventory & Decisions

## Project Scope

- **AMC:** ICICI Prudential Asset Management Company
- **Schemes (4):**
  1. ICICI Prudential Bluechip Fund (large-cap)
  2. ICICI Prudential Flexicap Fund (flexi-cap)
  3. ICICI Prudential ELSS Tax Saver Fund (ELSS, lock-in coverage)
  4. ICICI Prudential Balanced Advantage Fund (hybrid, different exit load mechanics)
- **Corpus target:** ~20 pages (within brief's 15–25 cap)
  - 4 schemes × 3 docs each (factsheet, KIM, scheme page) = 12 pages
  - 4 AMC-level pages (mutual funds FAQ, fees/charges, investor service for statements, Knowledge Centre)
  - 4 regulatory/industry pages (AMFI investor education, AMFI riskometer, SEBI mutual fund regulations, CAMS/KFintech statement help)

---

## Citation Hierarchy (locked)

1. **Scheme-specific numbers** (expense ratio, NAV, riskometer, benchmark) → factsheet (primary), KIM (fallback), scheme page (secondary fallback).
2. **Scheme rules** (minimum SIP, exit load, lock-in, objective) → KIM (primary), factsheet (fallback).
3. **General concept questions** (what is expense ratio, what is ELSS, what is riskometer) → AMFI (primary), ICICI Pru Knowledge Centre (fallback).
4. **Regulatory / investor rights** → SEBI (primary).
5. **Statement downloads** → ICICI Pru investor service page (primary), CAMS/KFintech (fallback if registrar-specific).

---

## Phase 1 — Ingestion

### Source Documents

- 20 pages from AMC, AMFI, SEBI, and registrar (CAMS/KFintech) as listed in Project Scope above.
- Every document captured with metadata: URL, document type, date/version, scheme name (where applicable), authority level.

### Chunking (locked)

- **Child chunks:** 100–200 tokens. Used for embedding and retrieval.
- **Parent chunks:** 600–800 tokens. Used when multiple children from the same parent are retrieved — parent is swapped in before sending to the LLM. Tune from eval results.
- **Overlap:** ~10% of child chunk size (small).
- **Splitter:** structure-aware (lean on headings, section markers, document structure) with recursive character splitting as fallback when structure-aware produces chunks outside the target size range.
- **Metadata schema (per chunk, 8 fields):**
  1. Source name
  2. Source type (factsheet / KIM / scheme page / AMC page / AMFI / SEBI / registrar)
  3. Source URL
  4. Date / version
  5. Scheme name (where applicable)
  6. Section heading the chunk came from
  7. Parent chunk ID
  8. Authority level (for citation hierarchy)

### Document Parsing (locked)

Parsing converts raw documents (PDFs and HTML) into clean structured text before chunking. Bad parsing produces bad chunks regardless of downstream quality.

- **PDF parser stack:**
  - **PyMuPDF (fitz)** as primary text extractor — fast, accurate for prose, zero cost.
  - **pdfplumber** for table-heavy sections — preserves tabular structure rather than mashing it into a single text blob.
  - Hosted/paid parsers (LlamaParse, Adobe PDF Extract) only as escalation if specific documents fail. No preemptive use.
- **Table handling:**
  - **Simple key-value tables** (fee structures, scheme attributes — most "tables" in factsheets are actually one-column-of-labels + one-column-of-values lists) → flatten to prose. Example: "Expense ratio: 1.2%. Exit load: 1% if redeemed within 12 months."
  - **Genuine multi-column tables** (top 10 holdings with name, sector, %, market cap) → preserve as markdown tables. Chunking must keep these whole (parent-sized unit, not split mid-row).
- **OCR fallback:**
  - Triggered when extracted text from a PDF page falls below ~100 characters (suggesting scanned content rather than text-encoded).
  - Tesseract used for English-language documents.
  - **Logged loudly** when triggered — silent OCR fallbacks mask source-quality issues.
- **HTML parser stack:**
  - **Trafilatura** as primary — purpose-built for article-content extraction, handles boilerplate (nav, ads, sidebars) automatically.
  - **BeautifulSoup with per-site CSS selectors** as fallback — for scheme detail pages where data lives in structured components Trafilatura might miss, or pages where Trafilatura strips too aggressively.
  - Performance verified sufficient for scale: ~50–200ms per page typical, ~1–5 seconds total for the ~8 HTML pages. Parsing happens once at ingestion, not per query. Not a bottleneck for eval runtime.
- **Output format: markdown** as the standard intermediate format.
  - Headings → `#`, lists → `-`, tables → markdown tables.
  - Both PyMuPDF and Trafilatura output normalized to markdown via a small post-processing layer.
  - `source_documents.parsed_text` holds markdown, not raw plain text.
  - Easy to inspect — opening the markdown shows parsing quality immediately.
- **Re-parsing strategy: manual.**
  - Documents update (factsheets monthly). For a project-scale corpus over a semester, manual re-ingestion is the right tier — at most 1–2 cycles during the project lifecycle.
  - Documented as a procedure in the README, not automated.
  - Cron jobs / change detection deferred to production scope.
- **Parsing failure handling:**
  - **Skip with logged warning** — failed documents don't halt ingestion, but they don't disappear silently either.
  - **Pre-launch ingestion report** (`ingestion_report.md`) generated listing every document with: source type, parsing status (success / partial / failed), character count extracted, number of chunks produced.
  - Manual review of the report before going live — decide which failures to address vs accept.

### Embeddings (locked)

Decisions, level by level:

- **Level 1 — Hosting:** Hosted API (not self-hosted).
- **Level 2 — Provider/model:** Voyage AI — `voyage-finance-2` (finance-domain-tuned, Anthropic-documented pairing with Claude).
- **Level 3 — Self-hosted models considered:** Not adopting (BGE / E5 / GTE rejected). Consistent with Level 1.
- **Level 4 — Dimension size:** 1024 (native output of voyage-finance-2; truncation not supported on this model, storage cost at corpus scale is negligible).
- **Level 5 — Domain vs general-purpose:** Domain-specific finance model. Only one embedding model can be used across the corpus and queries — beginner-friendliness handled at the system prompt and experience-level selector, not the embedding layer.
- **Level 6 — Query-side considerations:** Same embedding model (`voyage-finance-2`) used for both documents and queries. This is a constraint, not a choice — required for vector comparison to be meaningful. Query reformulation deferred to the retrieval phase.
- **Level 7 — Metadata prepending:** Yes — prepend scheme name and section heading to chunk text before embedding to improve retrieval precision (especially scheme disambiguation across similarly-structured documents).

### Storage (locked)

**Database:** PostgreSQL with `pgvector` extension.

**Metadata strategy:** Hybrid — filterable fields as typed columns, the rest as JSON.

**Tables:**

#### `source_documents`

Holds the full parsed text of each ingested document so re-chunking later doesn't require re-parsing PDFs.

| Column | Type | Notes |
|---|---|---|
| `document_id` | UUID PK | |
| `source_name` | TEXT | e.g. "ICICI Pru Bluechip Factsheet" |
| `source_type` | TEXT | factsheet / KIM / scheme_page / AMC_page / AMFI / SEBI / registrar |
| `source_url` | TEXT | |
| `date_version` | TEXT | e.g. "2025-10" for monthly factsheets |
| `is_latest` | BOOLEAN | TRUE for the current ingested version per `source_url`. Distinct URLs are independent documents (e.g. two AMFI pages both stay latest). Re-ingest of the same URL demotes prior rows for that URL only. Drives retrieval's default version filter via join on `source_documents`. |
| `scheme_name` | TEXT NULL | NULL for AMC-level / regulatory docs |
| `authority_level` | TEXT | Drives citation hierarchy |
| `parsed_text` | TEXT | Full parsed content of the document (markdown-formatted, per Document Parsing) |
| `ingested_at` | TIMESTAMPTZ | |

#### `parent_chunks`

Larger chunks (600–800 tokens) swapped in when multiple children from the same parent are retrieved. No embeddings.

| Column | Type | Notes |
|---|---|---|
| `parent_chunk_id` | UUID PK | |
| `document_id` | UUID FK → `source_documents.document_id` | |
| `text` | TEXT | The parent chunk content |
| `scheme_name` | TEXT NULL | Pulled out for filtering |
| `source_type` | TEXT | Pulled out for filtering |
| `authority_level` | TEXT | Pulled out for filtering |
| `metadata` | JSONB | section_heading, source_url, date_version, source_name |

#### `child_chunks`

Small chunks (100–200 tokens) that get embedded and searched.

| Column | Type | Notes |
|---|---|---|
| `child_chunk_id` | UUID PK | |
| `parent_chunk_id` | UUID FK → `parent_chunks.parent_chunk_id` | |
| `document_id` | UUID FK → `source_documents.document_id` | |
| `text` | TEXT | The child chunk content (with scheme name + section heading prepended pre-embedding) |
| `embedding` | vector(1024) | Voyage `voyage-finance-2` output |
| `scheme_name` | TEXT NULL | Pulled out for filtering |
| `source_type` | TEXT | Pulled out for filtering |
| `authority_level` | TEXT | Pulled out for filtering |
| `metadata` | JSONB | section_heading, source_url, date_version, source_name |

**Index:** HNSW or IVFFlat on `child_chunks.embedding`. B-tree indexes on `scheme_name`, `source_type`, `authority_level` for filtering.

#### `sessions`

Conversation state for context reignition. One row per session, updated as the conversation progresses.

| Column | Type | Notes |
|---|---|---|
| `session_id` | UUID PK | |
| `user_identifier` | TEXT NULL | Anonymous identifier if no login |
| `experience_level` | TEXT NULL | new / somewhat_familiar / expert |
| `current_state` | JSONB | The structured state file (facts established, schemes discussed, preferences, etc.) |
| `learnings_generated_at` | TIMESTAMPTZ NULL | Set when the user generates the post-chat PDF; NULL if never generated |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

#### `query_logs`

One row per turn. Captures everything needed for the thumbs-down → diagnose loop.

| Column | Type | Notes |
|---|---|---|
| `turn_id` | UUID PK | |
| `session_id` | UUID FK → `sessions.session_id` | |
| `experience_level` | TEXT | Denormalized — captures the level *at the time of the turn*. Required because mid-session level changes would corrupt analysis if only `sessions.experience_level` (current value) were available. |
| `user_question` | TEXT | |
| `retrieved_chunks` | JSONB | Array of {child_chunk_id, rank_pre_rerank, rank_post_rerank, similarity_score, text_snippet} |
| `final_prompt` | TEXT | The full prompt sent to the LLM |
| `raw_llm_output` | TEXT | Before any post-processing |
| `final_answer` | TEXT | What the user actually saw |
| `cited_chunk_id` | UUID NULL | The chunk cited in the answer, if any |
| `citation_flow` | JSONB | Citation enforcement audit trail: `{citation_present, cited_url, url_provenance_passed, required_regeneration, final_outcome, failure_mode}`. Feeds diagnostic queries. |
| `refusal_category` | TEXT NULL | NULL on factual answers; otherwise: `pii` / `out_of_scope` / `no_performance` / `thin_retrieval` / `mixed_factual_advisory`. |
| `latency_input_filters_ms` | INT | PII + out-of-scope + no-performance + query expansion |
| `latency_embedding_ms` | INT | Voyage embedding API call |
| `latency_retrieval_ms` | INT | Postgres semantic + lexical + RRF fusion |
| `latency_rerank_ms` | INT | Voyage rerank API call |
| `latency_generation_ms` | INT | Claude LLM call (sums across regeneration if any) |
| `latency_postprocessing_ms` | INT | Citation verification + response shaping |
| `latency_total_ms` | INT | End-to-end wall clock |
| `cost_usd` | NUMERIC(10, 6) | Per-query API cost (Voyage embed + rerank + Claude generation, summed). Feeds cost-budget tracking. |
| `created_at` | TIMESTAMPTZ | |

#### `feedback`

User thumbs up/down, linked to the specific turn.

| Column | Type | Notes |
|---|---|---|
| `feedback_id` | UUID PK | |
| `turn_id` | UUID FK → `query_logs.turn_id` | |
| `session_id` | UUID FK → `sessions.session_id` | |
| `rating` | TEXT | thumbs_up / thumbs_down |
| `comment` | TEXT NULL | Optional free-text |
| `created_at` | TIMESTAMPTZ | |

#### `pii_refusals`

PII detection events. Content is never stored — only the event metadata.

| Column | Type | Notes |
|---|---|---|
| `pii_refusal_id` | UUID PK | |
| `session_id` | UUID FK → `sessions.session_id` | |
| `pii_type` | TEXT | pan / aadhaar / account_number / otp / email / phone |
| `detected_at` | TIMESTAMPTZ | |

#### `session_turn_embeddings`

Embeddings of past turns within a session, used by context reignition's retrieval mode (triggered when session state exceeds ~5000 tokens).

| Column | Type | Notes |
|---|---|---|
| `turn_id` | UUID FK → `query_logs.turn_id` | |
| `session_id` | UUID FK → `sessions.session_id` | |
| `turn_text` | TEXT | `User: <question> \| Bot: <answer>` concatenated |
| `embedding` | vector(1024) | Voyage `voyage-finance-2` output (same model as document corpus) |
| `created_at` | TIMESTAMPTZ | |

**Relationships summary:**
- `source_documents` → `parent_chunks` (1:many)
- `parent_chunks` → `child_chunks` (1:many)
- `source_documents` → `child_chunks` (1:many, denormalized for direct lookup)
- `sessions` → `query_logs` (1:many)
- `query_logs` → `feedback` (1:1, optional)
- `sessions` → `pii_refusals` (1:many)
- `sessions` → `session_turn_embeddings` (1:many)
- `query_logs` → `session_turn_embeddings` (1:1)

**Note on intentional denormalization:** `source_url` lives in `source_documents` as the canonical record and also appears in `parent_chunks.metadata` and `child_chunks.metadata` JSONB for query convenience (avoids a join on every retrieval). Same for other source-level fields. This is deliberate, not a schema mistake.

---

## Phase 2 — Retrieval

### Hybrid Retrieval (locked)

- **Lexical algorithm:** BM25.
- **Lexical engine:** Postgres native full-text search (`tsvector` / `tsquery` with `ts_rank`). No new infrastructure beyond what's already in Postgres.
- **Semantic search:** pgvector similarity search against `child_chunks.embedding` (Voyage `voyage-finance-2`, 1024 dims).
- **Fusion method:** Reciprocal Rank Fusion (RRF) with k=60.
- **Candidate counts:** Top 20 from semantic search + top 20 from lexical search, fused via RRF into top 20 merged candidates passed to reranking.
- **Searched content:** Same modified text used for embedding (chunk text with scheme name + section heading prepended). One column, used for both semantic and lexical search.
- **Performance note:** Lexical search at corpus scale runs in single-digit milliseconds; negligible compared to embedding API (~100–300ms) and reranking (~200–500ms).

### Filtering by Metadata (locked)

- **When the filter runs:** Pre-filter via SQL `WHERE` clauses inside the retrieval query. Both semantic and lexical search operate on the filtered subset.
- **Scheme detection:** Hard-coded. Maintain a list of the 4 scheme names plus common variants (e.g., "Bluechip", "blue chip", "ICICI bluechip" all → "ICICI Pru Bluechip Fund"). Detector checks the query against this list and applies the `scheme_name` filter if matched. No LLM involvement in filter decisions.
- **Detector eval:** Separate eval added — throws realistic scheme-name variations at the detector and checks the correct filter gets applied. This is independent of answer-quality evals.
- **Authority-level filtering:** Not applied at retrieval. The citation hierarchy decides which source to *cite* among retrieved chunks — it's a post-retrieval step, not a pre-retrieval filter.
- **Zero-result behavior:** Strict — no fallback to unfiltered search. Refusal message is structured:
  1. If the query is ambiguous (could plausibly be a misspelling or shorthand for an in-scope scheme), ask for clarification ("Did you mean ICICI Pru Bluechip Fund?").
  2. Otherwise, acknowledge scope and redirect: list the 4 covered schemes, explain the requested scheme isn't in scope, link to the AMC's official factsheet directory.
  3. Distinguish "wrong scheme" (scope refusal) from "right scheme, no data" (factsheet link).
- **Version filtering:** Join `child_chunks` to `source_documents` where `is_latest = true`. Version competition is per `source_url` only — distinct URLs never demote each other. A scheme may have multiple latest documents (e.g. digital factsheet URL + TER CSV URL). Older ingests of the same URL remain with `is_latest = false` for traceability.

### Reranking (locked)

- **Reranker model:** Voyage `rerank-2`. Single-vendor consolidation with embeddings (`voyage-finance-2`), same SDK / API key / auth pattern.
- **Input size:** 20 candidate child chunks (output of hybrid retrieval + filtering).
- **Output size:** Top 3 unique parents passed to the LLM.
- **Parent swap order:** Swap happens *after* reranking. Flow: rerank 20 children → take ordered list → deduplicate by parent (keep highest-ranked child per parent) → swap each surviving child for its parent → pass top 3 parents to LLM.
- **Why this order:** Reranking on small precise child chunks plays to their strength (sharp scoring). Parent swap happens at final assembly for context, not at scoring. Multi-child-same-parent collisions are treated as signal — pull next-ranked unique-parent child to maintain 3 distinct parents.
- **Latency budget:** Accept ~300–500ms for reranking. If evals later show this is too much, levers are (a) reduce candidates from 20 → 10, (b) switch to `rerank-2-lite`. No preemptive trimming.
- **Failure handling:** Retry once with short backoff. On second failure, fail open — fall back to RRF order from hybrid retrieval, skip reranking, log the event for diagnostics. Reranking improves quality but isn't strictly required for the system to function.

### Parent Retrieval (locked)

- **Parent size:** 600–800 tokens (locked in chunking).
- **Parent definition:** Structural — parent = the natural heading/section-bounded block in the source document. Recursive fallback when a section exceeds ~800 tokens, splitting it into multiple parent-sized blocks. Preserves topical coherence, avoids parents that straddle unrelated sections (e.g., "exit load" and "minimum SIP").
- **Self-parent for short docs:** Every child has a parent row. For very short documents or sections where the entire content fits in a single child (100–200 tokens), the parent row is a copy of the child (minus the embedding). Keeps retrieval logic uniform — `parent_chunk_id` on `child_chunks` is never null, swap is always performed.
- **Order sent to LLM:** By reranker rank, highest-ranked parent first. Respects reranker's relevance judgment; avoids over-weighting less-relevant chunks via positional bias.
- **Metadata sent with parents:** Text + metadata header. Each parent prepended with `[Source: <source_name>, <date_version> | URL: <source_url>]` before the chunk text. Enables the LLM to output the correct citation URL alongside the answer without external reconstruction.

### Query Expansion (locked)

- **Expansion method:** Synonym dictionary maintained in application code (no LLM-based expansion). Maps user-side terms to document-side equivalents — e.g., "annual fee" ↔ "expense ratio" ↔ "TER", "withdrawal" ↔ "redemption", "minimum holding period" ↔ "lock-in".
- **Expanded query usage:** Single merged query (original + variants concatenated into one string), passed to retrieval.
- **Expansion trigger (hybrid — Option B):** Different behavior per search type, grounded in how each handles query length.
  - **Semantic search:** Always expand. The embedding captures combined meaning; extra related terms usually help.
  - **Lexical search (BM25):** Conditional expansion. Expansion only applied when a user-side synonym is detected in the query. Avoids diluting BM25's term-frequency / document-length scoring with unnecessary terms.
  - Single synonym dictionary feeds both; application logic decides whether to expand at the moment of querying.
- **Where the logic lives:** Application code. Dictionary maintained alongside, easy to extend as new user phrasings show up in logs.
- **Eval:** Dedicated eval for the expander itself (separate from answer-quality evals). Scenarios in `evals.md`; run as automated tests in this repo. Test cases:
  - Casual-term query → expansion adds document-side equivalents (semantic) / triggers expansion (lexical).
  - Formal-term query → semantic still expands (by design); lexical does not expand.
  - No-match query → no expansion happens, original query passes through.

### Grounding (locked)

- **Hard reranker-score threshold:** If top reranker score is below the threshold, skip generation and return a structured refusal. Hard threshold (not soft, not absent) — grounding prompts alone are unreliable in domains where the LLM has plausible-sounding general knowledge (mutual funds is one such domain).
- **Threshold tuning:** Placeholder value set at ingest time. Real value found by threshold sweep eval (Phase 5) — balances false-refusal rate against hallucination rate. Not committed to upfront.
- **Refusal message when threshold not met:** Structured, reusing the pattern from filtering's scope refusal. Includes:
  - "I couldn't find a clear answer to that in my sources."
  - Suggestion to rephrase if the question seems in-scope but phrased unusually.
  - Pointer to the AMC's official factsheet directory or relevant authority for further info.
- **Grounding instructions in prompt:** Explicit — "answer only from retrieved sources," "say so clearly if sources don't contain the answer," "every factual claim tied to a source ID." Exact wording deferred to Phase 3 (system prompt design).
- **Citation enforcement:** Programmatic verification on the LLM's output before display. Check: (a) a citation is present, (b) the cited URL matches one of the retrieved chunks' source URLs. If missing or mismatched, regenerate once. If still missing after regeneration, fall back to a structured refusal. Brief explicitly requires "one clear citation link in every answer" — trust-the-prompt is insufficient for a hard requirement.

---

## Phase 3 — Generation

### PII Filter (locked)

- **Position in pipeline:** Pre-retrieval. If PII is detected in the user's input, short-circuit immediately — no embedding, no search, no LLM call, no storage of the offending content. Optional post-LLM check as belt-and-braces against any PII leaking through generation.
- **Detection method:** Regex / pattern matching on the brief's explicit list — PAN (5 letters + 4 digits + 1 letter), Aadhaar (12 digits in known formats), account numbers (numeric ranges), OTPs, emails (contains `@`), phone numbers (country-code-aware patterns). No LLM-based detection — closed list of well-defined formats, regex handles deterministically with no latency cost.
- **Action on detection:** Hard refusal with explanation. Message pattern: "I noticed your message contains [type of PII]. For your privacy and safety, I can't process queries containing personal information. Please rephrase your question without including PAN, Aadhaar, account numbers, or other personal details." Sanitize-and-continue rejected as too risky in a finance context.
- **Logging when PII is detected:** Event logged but content never stored. Capture: timestamp, session ID, PII type detected (PAN / Aadhaar / email / etc.). The actual PII value is dropped. Stored in the dedicated `pii_refusals` table (locked under Storage).
- **Escalation:** If logs later show users routinely bypassing regex with spelled-out variants or other patterns, revisit with Presidio (Microsoft's PII detection library). No preemptive over-engineering.

### Out-of-Scope / Opinion Refusal (locked)

- **Refusal categories explicitly enumerated in the system prompt** (4–6 concrete examples, not just an abstract "no advice" rule):
  - Investment recommendations — "should I buy X," "is X a good investment," "is this scheme right for me"
  - Portfolio advice — "should I rebalance," "should I switch from X to Y," "what % should be in equity"
  - Predictions / forecasts — "will this fund go up," "what return will I get," "is the market going to crash"
  - Tax planning advice — generic "how should I save tax" (distinct from factual ELSS tax-benefit questions)
  - Comparisons that imply judgment — "which fund is better, X or Y" (judgment), distinct from "what are the expense ratios of X and Y" (facts)
  - Personal finance questions — "I have 10 lakhs, where should I invest"
- **Detection method (hybrid):**
  - Rule-based pattern matching for obvious advice-seeking phrases ("should I", "recommend me", "is X better than Y", "what should I invest in"). Caught here → short-circuit refusal, no retrieval.
  - LLM classification via system prompt for ambiguous cases that escape pattern matching. The prompt instructs the LLM to refuse if the query is advisory.
  - Two layers, two chances to catch.
- **Position in pipeline:** Runs after the PII filter. PII first (security), out-of-scope second (scope).
- **Refusal message (structured):**
  1. Acknowledge what the user asked.
  2. Explain the bot's scope — facts only, no advice.
  3. Redirect to educational source per citation hierarchy (AMFI investor education for general advice questions, SEBI investor charter for regulatory-flavored advice).
  4. Invite the user to ask a factual version of the question (e.g., "I can share the expense ratio, exit load, or other characteristics if useful").
- **Logging:** Full logging including query content. Out-of-scope queries are useful signal, not sensitive — track query text, detection method (rule vs LLM), refusal category, session/turn IDs. Reveals what users actually want from the bot.
- **Eval:** Dedicated eval for the refusal detector (separate from answer-quality evals). Scenarios in `evals.md`; run as automated tests in this repo. Test cases:
  - Clearly advisory queries → all caught and refused.
  - Clearly factual queries → none falsely flagged as advisory.
  - Ambiguous queries → behavior tested and documented.

### No-Performance-Claims Rule (locked)

- **Scope of refusal — three sub-categories, all refused:**
  - **Performance computation** — "what's the average annual return of Fund X over 5 years," "compare returns of Fund X and Fund Y." Refuse and redirect to factsheet.
  - **Performance prediction** — "what return will I get," "will this fund outperform." Already covered under out-of-scope refusal; no separate handling needed here.
  - **Performance lookup** — "what does the factsheet say about returns." Even though the factsheet technically states returns, bot does not quote them. Always redirects to the factsheet. Reason: performance numbers carry "subject to market risks" disclaimers, period qualifications, and context the bot can't reliably provide in a 3-sentence answer.
- **Detection method (hybrid):**
  - Rule-based pattern matching on performance vocabulary — "return," "CAGR," "performance," "yield," "gain," "annualized," "alpha," "beta," "how much did X earn."
  - LLM classification via system prompt as a second layer for cases that escape patterns.
  - Same two-layer pattern as out-of-scope refusal.
- **Refusal message (structured):**
  1. Acknowledge what was asked.
  2. Explain that the bot doesn't share or compute performance figures.
  3. Redirect to the specific scheme's factsheet (or AMC's factsheet directory if ambiguous).
  4. Offer alternative non-performance facts the bot *can* share (expense ratio, exit load, fund category, etc.).
- **Factsheet link selection:**
  - Reuses scheme detection from filtering (the hard-coded scheme list + variants).
  - Scheme clearly identified → link to that specific factsheet.
  - Scheme ambiguous → link to AMC's general factsheet directory.
  - No new logic needed.
- **Logging:** Full logging including query content. Performance questions are useful signal — high volume means the bot's positioning may need clarification in onboarding.
- **Eval:** Dedicated eval for the performance detector. Scenarios in `evals.md`; run as automated tests in this repo. Test cases:
  - Clearly performance queries → all caught and refused.
  - Clearly non-performance queries → none falsely flagged.
  - Ambiguous cases → behavior tested and documented.

### System Prompt Structure (locked)

- **Static / dynamic separation:**
  - Static block at the top: bot identity, scope rules, refusal categories, grounding rules, citation rules, answer format rules. Written once, reviewed carefully, version-controlled.
  - Dynamic block at the bottom: user's experience level, relevant conversation state, retrieved sources, current question.
  - Rationale: LLMs attend most strongly to the beginning and end of input — identity/rules at top stay in mind throughout; question at the very end is what the model needs to answer last.
- **Section ordering in the assembled prompt:**
  1. Identity (bot's role, AMC, schemes covered).
  2. Scope rules (facts only; enumerated refusal categories from PII / out-of-scope / no-performance sections).
  3. Grounding rules (answer only from retrieved sources, say "I don't have that information" when sources are thin, every claim tied to a source).
  4. Citation rules (exactly one citation link per answer, must match a retrieved source's URL, format specified).
  5. Answer format rules (length driven by quality and experience level per the Answer Length Policy — no hard sentence cap; runaway safety net only; include `Last updated from sources: <date>`; citation line on its own).
  6. User's experience level (dynamic, from session).
  7. Conversation state summary (dynamic, from context reignition if any).
  8. Retrieved sources (top 3 parents with metadata headers — kept adjacent to the question).
  9. User's current question (final block).
- **Experience level — concrete instruction strings per bucket:**
  - **Beginner ("new"):** "Use plain language. When using terms like 'expense ratio,' 'exit load,' 'NAV,' briefly explain what they mean in parentheses. Keep tone friendly and encouraging."
  - **Somewhat familiar:** "Use standard terminology directly. Brief context where useful but don't over-explain. Tone is neutral and helpful."
  - **Expert:** "Use precise terminology without explanation. Tone is direct and concise. Skip context the user likely already knows."
- **Few-shot examples — 12 total, conditional injection:**
  - **4 categories × 3 levels = 12 examples** stored in the prompts file.
  - Categories: (1) factual answer, (2) out-of-scope refusal, (3) thin-retrieval refusal, (4) mixed factual + advisory.
  - Per query, only the **4 examples matching the current user's level** get injected (based on session state). Beginner-level user → 4 beginner-flavored examples; expert-level user → 4 expert-flavored examples.
  - Rationale: 12 examples in every prompt would be 600–1200 tokens of overhead — conditional injection keeps each prompt to 4 relevant examples while maintaining the full library system-wide.
- **Mixed factual + advisory queries (Option B):**
  - Detection: same hybrid pattern as out-of-scope refusal — phrase patterns for advisory clauses ("should I", "is it good", "is now a good time") catch most cases; LLM in the system prompt as fallback.
  - Behavior: answer the factual part with proper citation, then explicitly decline the advisory part with a redirect (factsheet, SEBI investor advisor, AMFI investor education).
  - Example shape: "Bluechip Fund's expense ratio is X% (factsheet, last updated [date]). I can't advise whether to invest — for that, consult a SEBI-registered advisor. [Link]."
  - Citation rule still applies to the factual portion; the refusal portion doesn't need a citation (it's a scope statement, not a factual claim).
  - Logged as a distinct category (`mixed_factual_advisory`) in `query_logs` for separate signal tracking.
  - Dedicated few-shot example pattern per level (already counted in the 12-example total above).
- **Prompt file location and versioning:**
  - Lives at `prompts/system_prompt.md` in the repo.
  - Sections clearly marked with dynamic-injection placeholders (e.g., `{{retrieved_sources}}`, `{{experience_level_instructions}}`, `{{few_shot_examples}}`).
  - Version-controlled via git, reviewable via diff, supports A/B testing by swapping files.
- **Multi-prompt strategy:**
  - Single main prompt for the answer path (the assembled prompt described above).
  - Static refusal templates for filter-rejected queries (PII, out-of-scope detected by patterns, no-performance detected by patterns). No LLM call needed for these — return the static template directly. Cleaner architecture, lower cost.
  - LLM only invoked when the query passes input filters and retrieval returns results above the grounding threshold.

### Answer Length Policy (locked — deliberately diverges from brief)

- **Hard sentence count: dropped.** The brief's "≤3 sentences" rule is not enforced. Reason: it conflicts with the locked experience-level design (beginner-mode parenthetical explanations, term clarifications, encouraging tone) and would force lower-quality answers for users who genuinely need more context. Brief is ungraded; user experience takes precedence here.
- **Quality, not length, is the constraint.** Per-level instructions in the system prompt drive natural answer length:
  - Expert level: terse, often 1–3 sentences.
  - Somewhat familiar: standard, typically 2–5 sentences.
  - Beginner: room to define terms, add necessary context, naturally 3–8 sentences.
  - The LLM produces what the question genuinely needs at the user's level. The system does not force compression.
- **Runaway safety net (only):** Loose backstop to catch pathological output (rambling, repetition, unprompted essays). Cap set generously — ~250 words / ~8 sentences on the answer body alone. This is *not* a quality control mechanism; it's a safeguard against the LLM going off the rails.
- **No regeneration on length:** The LLM's natural output is sent to the user as-is, unless the runaway cap is hit. No length-based re-prompting, no "make it shorter" feedback loops. Avoids the failure mode where regeneration prompts compromise answer quality to satisfy a count.
- **Runaway cap behavior:** If the answer body exceeds the safety net, fall back to a complete pre-written message ("I have detailed information about this, but the full answer is unusually long. For complete details, see the official factsheet: [link]. Last updated from sources: [date]."). Citation and metadata preserved. Never a mid-sentence truncation.
- **Architectural commitment — no mid-sentence cutoffs:** The LLM call is always given enough token budget to finish naturally. Verification (if any) is post-generation on the complete output. The only paths are: (a) send the complete response, or (b) send a complete pre-written fallback. Truncation never happens.
- **Citation link and "Last updated from sources: <date>" line:** Excluded from the safety net's word/sentence count. They are metadata wrapping the answer body.
- **Smart sentence packing as a soft preference (not enforcement):** Few-shot examples demonstrate dense, multi-fact sentences where appropriate, so the model learns to be efficient without being forced to be brief. Users get tight answers when the question is tight; longer answers when the question needs depth.

### Citation Enforcement (locked)

- **Citation format:** End-of-answer line, on its own. Pattern: `Source: [<source_name>, <date_version>](<source_url>)`. Sits alongside the `Last updated from sources: <date>` line as metadata wrapping the answer body. Clean visual separation, easy to verify programmatically, consistent across all answers.
- **Which source to cite when multiple are relevant:** Citation hierarchy (locked earlier) decides — primary source for the type of fact being cited. Recap:
  - Scheme-specific numbers → factsheet (primary).
  - Scheme rules → KIM (primary).
  - General concepts → AMFI (primary).
  - Regulatory framing → SEBI (primary).
  - Statement downloads → ICICI Pru investor service page (primary).
  - When an answer pulls multiple facts, cite the primary source for the *main* fact the user asked about.
- **Programmatic verification checks (per answer):**
  - **Format compliance:** Regex check that the citation line exists at the end in the expected format.
  - **URL provenance:** The cited URL must be a member of the retrieved chunks' `source_url` set. Model cannot invent a URL, even one that looks plausible.
  - **Alignment (citation actually supports the claim):** Not enforced per-query. Handled via sample-based audit in evals. Per-query LLM-as-judge alignment checks add latency/cost and the grounding prompt + hierarchy already bias strongly toward correct citations. Escalate to per-query alignment only if audits show drift.
- **Failure handling — differentiated by failure mode:**
  - **Citation format wrong but URL correct:** Reformat in code (cheap fix, no regeneration). Wrap the URL in the expected pattern and proceed.
  - **Citation missing entirely:** Regenerate once with explicit instruction to include citation.
  - **Citation present but URL not in retrieved set (invented URL):** Regenerate once with explicit instruction to use only URLs from provided sources. **Log loudly** — this is the dangerous case.
  - **Persistent failure after one regen:** Fall back to a structured refusal that includes a citation pointing to the appropriate authoritative source per the hierarchy.
- **Refusal messages and citation enforcement:**
  - Citation requirement applies only to **factual answer bodies**.
  - Refusal messages (PII, out-of-scope, no-performance, thin-retrieval, mixed-query refusal portion) include redirect links per their locked patterns, but those redirect links are **not subject to citation verification** — they're scope statements, not factual claims.
  - Response type tag in LLM output (e.g., `[FACTUAL]` or `[REFUSAL]`) drives the verifier path. Tag is stripped before display to the user.
  - For mixed factual + advisory queries: factual part must have citation per the rule; refusal portion does not.
- **Logging — `query_logs.citation_flow`** (JSONB column, locked under Storage) captures:
  - Citation present (boolean).
  - Cited URL.
  - URL provenance check passed (boolean).
  - Required regeneration (boolean).
  - Final outcome (`cited` / `cited_after_regen` / `fallback_refusal`).
  - Failure mode (if any): `format_only` / `missing` / `invented_url`.
  - Feeds the diagnostic queries in `diagnostics/`.

---

## Phase 4 — Product Layer (Backend)

*UI design (welcome screen, chat interface, suggested questions, disclaimer placement, mobile responsiveness) is carved out as a separate later concern. This phase covers backend mechanics, prompt logic, and storage for the product-layer features.*

### Experience-Level Selector — Backend (locked)

- **Capture timing:** Upfront on session start, skippable. Every session has a level value from message 1 — if the user picks, that value is stored; if the user skips, the default is applied immediately. No conditional "what if level isn't set" logic downstream.
- **Default level when user skips:** `somewhat_familiar`. Beginner default risks patronizing experienced users; expert default risks confusing newcomers. The middle bucket does the least harm to either edge.
- **Mutability mid-session:** Mutable via explicit user command only. Recognized commands: "explain simpler," "more technical," "switch to expert mode," etc. Auto-detection (silent level changes based on follow-up phrasing) rejected as too brittle — user can't predict the bot's behavior. On command:
  - Update `sessions.experience_level`.
  - Apply from the next turn forward.
  - Brief acknowledgment to the user ("Got it, switching to simpler explanations").
- **Prompt-side wiring:** Instruction strings live in `prompts/experience_levels/<level>/instructions.md`, one file per level. Main `prompts/system_prompt.md` references via `{{experience_level_instructions}}` placeholder; application code substitutes the relevant file's contents at prompt-assembly time.
- **Few-shot organization:** `prompts/experience_levels/<level>/examples/<category>.md` — level-first folder structure. Per query, only the 4 examples matching the current user's level get injected (4 categories × 1 level = 4 examples). When changing a level's behavior, everything for that level lives in one place.
- **Per-turn logging:** `experience_level` column added to `query_logs` as a denormalized field — captures the level *at the time of the turn*. Required because mid-session level changes would corrupt analysis if only `sessions.experience_level` (current value) were available. Slight redundancy is intentional.

### Context Reignition Mechanics (locked)

- **State contents (hybrid):**
  - **Structured facts (always loaded):** user's experience level, schemes they've asked about, refusal events that occurred (so the bot doesn't keep re-refusing the same advisory question without acknowledgment), any explicit preferences ("explain simpler" command). Append-only — doesn't drift.
  - **Recent raw turns (rolling window):** last 5 turns kept verbatim. Used for reference resolution ("what about its expense ratio" → "its" refers to the fund from earlier).
  - **No LLM-generated summary prose.** Rejected because LLM-regenerated summaries drift between turns; structured facts are append-only and stable.
  - Older turns beyond the rolling window are still in `query_logs` but not loaded by default — retrieval mode handles them if needed.
- **Fact extraction:** Rule-based only. Reuses existing detection — scheme detection from filtering, refusal categorization from input filters, level changes from explicit commands. No LLM call per turn. Deterministic and debuggable.
- **Dual-mode switching:**
  - **Load-whole mode (default, short sessions):** entire state file loaded into context every turn.
  - **Retrieval mode (long sessions):** triggered when state size crosses ~5000 tokens. Tunable threshold. Structured facts still loaded whole; raw turns become retrieval-only.
- **Retrieval-mode mechanics:**
  - Raw turns are embedded with Voyage `voyage-finance-2` (same model as document corpus) and stored in the `session_turn_embeddings` table.
  - Per-turn retrieval scoped to the current session pulls only the most relevant past turns for the current question.
  - Two pgvector lookups per turn (document corpus + session turns) — negligible latency at session scale.
- **Compact-and-index step (one-time per session):** Triggered at end-of-turn when state size first crosses the threshold. Steps:
  1. Embed all existing raw turns in that session (back-embed).
  2. Future turns also embed at end-of-turn.
- **`session_turn_embeddings` table:** Defined in the Storage section. Holds session-scoped turn embeddings (Voyage `voyage-finance-2`, 1024 dims) for retrieval-mode lookups.
- **Turn-embedding granularity:** Each "turn" in the embedding index is the user question + bot answer concatenated as a single string. Surfaces relevant past exchanges, not just relevant past questions or answers in isolation.
- **Session expiry:** 24 hours of inactivity. State cleared after expiry. A user returning after a day is functionally a new session — intent has likely shifted and stale state can mislead. Consistent with the locked decision that cross-session memory is out of scope.

### Selective Warmth (locked)

- **Where warmth rules live:** Folded into the existing per-level instruction files (`prompts/experience_levels/<level>/instructions.md`). No new prompt file. Warmth varies meaningfully by level, so keeping each level's full voice in one place avoids drift.
- **No user name capture.** No login system exists, and capturing a name via an explicit prompt at session start adds friction for no real value. No `{{user_name}}` placeholder in the system prompt. Warmth lives in tone and affirming phrases only, not name use. The `sessions.user_identifier` column remains for session identification (anonymous UUID), not human name.
- **Concrete warmth rules per level (encoded explicitly in each level's instruction file):**
  - **Beginner ("new"):**
    - Affirming phrases: used when the user asks a genuinely thoughtful question or shows hesitation. Examples: "Good question to think about," "That's worth understanding clearly." Avoid generic praise like "Great question!" on every turn.
    - Tone: warm, encouraging, patient.
    - Anchor warmth on the user's **curiosity**, not their **decisions** — never "great that you're considering this fund."
  - **Somewhat familiar:**
    - Affirming phrases: minimal — only when the user explicitly expresses confusion or asks a non-obvious question.
    - Tone: neutral and helpful. Warm but not effusive.
  - **Expert:**
    - Affirming phrases: avoid entirely. Experts find them patronizing.
    - Tone: direct, concise, peer-like. Answer first, no preamble.
- **Detection of warmth-fitting moments:** Pure LLM-side, guided by the per-level rules. No pre-processing signals (hesitation regex, complexity heuristics, etc.) — too fragile, too many edge cases. The LLM reads conversational nuance better than rules do.
- **Eval for warmth application:** Scenarios in `evals.md`; run as automated tests in this repo. Not willing to blindly trust the LLM on consistency. Test cases:
  - Beginner-level user, genuinely complex question → warmth applied appropriately.
  - Expert-level user, same question → no warmth (matter-of-fact).
  - Same user level, similar questions in a row → no repetition of the same warmth pattern (e.g., "great question!" every turn = failure).
  - User shows hesitation cues → LLM detects and responds in kind.
  - User is matter-of-fact → LLM stays matter-of-fact.
  - **Escalation:** If evals show drift or inconsistency, move to hybrid (pre-processing signals + LLM judgment). Pure LLM-side is the starting position, not a permanent commitment.
- **Warmth in refusals:** Refusal templates are static (returned without an LLM call). Warmth is baked into the template wording itself — the locked refusal structure (acknowledge → explain → redirect → invite rephrase) is naturally polite. No extra warmth additions, no LLM involvement, no `{{user_name}}`.
- **For mixed factual + advisory queries:** Factual part goes through the LLM and uses normal per-level warmth rules; the advisory refusal portion follows the static refusal template tone.
- **Logging warmth usage:** No separate logging field. If patterns need analysis later, query the `query_logs.final_answer` text. Adding flag columns for undefined future analysis is premature.

### Post-Chat Learnings Document — Backend (locked)

- **Generation timing:** On-demand only. Triggered by an explicit user action (UI carved out). Backend reads the session's `query_logs` and produces the document. No automatic generation on session expiry, no continuous regeneration per turn.
- **Document structure (six sections):**
  1. **Header** — title ("Your conversation with the ICICI Pru FAQ bot"), date, disclaimer summary.
  2. **Key facts you learned** — bulleted summary of substantive facts, grouped by scheme then by topic (expense ratio, exit load, etc.). This is the main value-add of the document.
  3. **Conversation transcript (collapsible)** — full Q&A pairs.
  4. **Sources referenced** — list of every URL cited during the conversation.
  5. **What wasn't covered** — refusals noted (e.g., "I asked about returns; the bot redirected to the factsheet for that"). Useful self-awareness for the user.
  6. **Full disclaimer** — static, fuller version.
- **Summarization approach — light LLM reformatting with strict prompt:**
  - LLM extracts factual claims from prior bot answers in this session.
  - Substantive content (numbers, dates, scheme rules) must use **exact wording** from the original answer. Only minimal connecting words for readability may be added.
  - Facts grouped by scheme, then by topic within each scheme.
  - Citation URLs preserved alongside the facts they support.
  - No fact may appear in the document that wasn't in the original answers — no inference, no paraphrasing of substantive content.
  - **Programmatic sanity check:** coarse word-overlap check confirms each extracted fact's substantive content appears verbatim somewhere in the source answers. Catches gross drift; not perfect but good enough at this scale.
- **Disclaimer placement and wording:**
  - **Dual placement:** brief version at the top (header), fuller version at the bottom.
  - **Static template wording, not LLM-generated.** Locked in `templates/learnings_document_disclaimer.md`. Regulatory-flavored language must not vary across documents.
  - Content covers: factual summary not investment advice; facts captured at a specific date and may have changed; consult a SEBI-registered advisor for investment decisions; AMC's official factsheet is the authoritative source.
- **File format: PDF.**
  - Generated server-side from an HTML template via WeasyPrint (or equivalent HTML→PDF converter).
  - Reasoning: in a finance context, PDF is what users expect from official-looking documents (factsheets, account statements). Format itself signals "this is something to keep." Universal device support — no "how do I open this" friction. Print-ready, share-ready, archive-ready.
  - User downloads the PDF to their device — that copy is permanent and theirs.
- **Server-side retention:**
  - Server keeps the generated PDF on disk for ~1 hour after generation (covers download retries on flaky networks).
  - After 1 hour, server-side copy is deleted. The user's downloaded copy is the persistent artifact, not the server's.
  - Folder structure: `/data/learnings/<session_id>/document.pdf`.
- **No threshold gate on session length:** If a user explicitly asks for a document, the document is generated, even for short sessions. The header acknowledges what was discussed; thin content is fine being thin. No arbitrary "your conversation is too short" refusal.
- **Logging:** `learnings_generated_at` timestamp field added to `sessions` (nullable). Useful product signal — how often do users actually generate the document, do certain session patterns correlate with generation. Flag field is simpler than a new table.

---

## Phase 5 — Operations

### Eval Suite

- **Owned end-to-end in this repo.** Structure taxonomy, generate eval data, define pass/fail criteria, run judging mechanics, and store results in `evals/results/`.
- **Inputs from this build (the evals already called out throughout):**
  - Scheme detector eval (filtering).
  - Query expansion eval (semantic always-expand, lexical conditional).
  - Out-of-scope detector eval.
  - No-performance detector eval.
  - Selective warmth eval (with escalation path to hybrid detection if drift shows).
  - Grounding threshold tuning eval (sweep balancing false-refusal vs hallucination).
  - Citation consistency eval (same question → same citation).
  - Source overlap eval (how the bot handles facts present in multiple documents).
  - Answer-quality eval on the brief's example questions.
  - Regulatory verbatim verification eval (mandatory disclaimers appear unchanged where required).
- **Runbook:** `docs/EVAL_SUITE_BRIEF.md` and `evals.md`. Per-feature inputs are listed throughout this document.

### Diagnostic Queries (locked)

Pre-written SQL queries against `query_logs` and related tables, so when something fails, debugging doesn't require writing SQL from scratch under pressure.

- **Four diagnostic categories** with 3–5 pre-built queries each:
  - **Retrieval diagnostics:**
    - Turns where no chunk scored above the grounding threshold (bot refused due to thin retrieval).
    - Turns where the cited chunk wasn't in the top-3 reranked set.
    - Thumbs-down turns where the correct chunk wasn't retrieved.
    - Distribution of top-1 similarity scores across all turns (feeds threshold tuning).
  - **Reranking diagnostics:**
    - Turns where the top-1 hybrid-retrieval candidate dropped below top-3 after reranking.
    - Turns where parent-deduplication collapsed multiple children into one parent.
    - Reranker latency distribution (p95/p99 outliers).
  - **Generation diagnostics:**
    - Turns where regeneration was triggered, broken down by reason (citation missing, invented URL, runaway length, etc.).
    - Turns where the final answer was the structured fallback (regeneration also failed) — persistent failures needing manual review.
    - Turns where the LLM's raw output differed substantially from the final answer.
  - **Citation diagnostics:**
    - Turns where the cited URL wasn't in the retrieved chunks' source URL set (invented-URL failure — high-severity).
    - Citation hierarchy adherence per turn.
    - Same question (by similarity) across sessions getting different citations.
- **Thumbs-down dedicated query family:**
  - `thumbs_down_review.sql` — pulls full turn context (question, retrieved chunks, rerank order, final answer, citation, latency) for recent negative-feedback turns.
  - `aggregate_thumbs_down_by_failure_mode.sql` — auto-classifies failure stage based on logged fields (retrieval problem vs reranker problem vs generation problem vs citation problem).
- **Storage and access:**
  - SQL files in `diagnostics/`, one query per file, parameterized for date ranges or session IDs.
  - Thin CLI wrapper for convenience (`diag <query-name> [--params]`).
  - Files version-controllable, copy-pasteable, run anywhere a SQL client connects.
- **Run pattern:**
  - On-demand for individual queries (investigation triggered by a specific failure).
  - One scheduled "operational health summary" report rolling up high-severity counts (invented URLs, regeneration rate, thumbs-down rate, refusal rate). Either one SQL file producing the rollup, or a small script assembling individual query results into a markdown summary.
  - No per-query alerts/notifications — operational-scale infrastructure, overkill for this project.
- **Scope discipline:** ~15–20 pre-built queries covering predictable debugging paths. Ad-hoc SQL handles unusual cases. Avoid pre-building queries that may go stale.

### Regulatory Research Output (locked)

Regulatory content is one of the few places where being wrong is worse than being incomplete. The bot operates in a SEBI/AMFI-regulated domain and must incorporate current required disclaimers, scope-defining language, and authoritative redirects.

- **Three categories of regulatory content:**
  - **Mandatory disclaimers** — text that SEBI/AMFI rules require in mutual fund communication (e.g., the standard market-risk disclaimer).
  - **Scope-defining language** — bot-specific positioning (not an advisor, not directly regulated as a chatbot, facts captured at a specific date).
  - **Authoritative redirects** — official resource URLs (SEBI investor charter, AMFI investor education, SEBI-registered advisor lookup, grievance portals).
- **Template structure:**
  - `templates/regulatory/mandatory_disclaimers.md` — verbatim regulatory text.
  - `templates/regulatory/scope_statements.md` — bot positioning.
  - `templates/regulatory/authoritative_links.md` — official resource URLs with descriptions.
- **Where each category lives in the system:**
  - **Mandatory disclaimers** → UI header/footer, post-chat learnings document (top + bottom), performance refusal messages.
  - **Scope-defining language** → system prompt (identity section), UI welcome line, post-chat document header.
  - **Authoritative redirects** → refusal message templates (already locked), citation hierarchy fallbacks.
- **Research approach — hybrid:**
  - **Draft at build time** via research (web search / official sources), pulling current SEBI and AMFI guidelines.
  - **Manual review pass** before shipping — non-negotiable. Spot-checks: mandatory disclaimer wording is verbatim from authoritative source; scope statements don't overclaim regulatory standing; redirect URLs are official (SEBI.gov.in, AMFI.com), not third-party blogs.
- **7-item research target list:**
  1. Standard market-risk disclaimer — exact current SEBI wording, and where it must appear.
  2. Performance disclaimers — required wording when performance is referenced (the bot doesn't compute performance, but documents it references contain it).
  3. AMC-specific disclaimers — any statutory language ICICI Prudential requires alongside their content.
  4. Investor charter references — SEBI's investor charter URL and scope.
  5. Investor grievance redressal — pointers to SEBI's SCORES portal and AMFI's grievance mechanism, used in post-chat document footer.
  6. Advisor referral language — exact phrasing when redirecting to SEBI-registered investment advisors (avoid inadvertently endorsing specific advisors).
  7. "Last updated" framing — how to communicate that information was captured at a specific date and may have changed.
- **Update strategy:**
  - One-time research at build.
  - README documents an annual review expectation (or trigger on material SEBI/AMFI changes).
  - Scheduled re-research deferred to production scope.
- **Verbatim verification eval:**
  - Programmatic check that mandatory disclaimers appear **verbatim** wherever required (UI footer, learnings document, performance refusal messages).
  - Regex/string match against the loaded template — paraphrased versions don't meet the requirement.
  - Added to the eval inputs in `evals.md` (P5-05).

### Latency / Cost Budget Thresholds (locked)

Concrete numbers anchoring the "deliberate, only add layers users notice" principle.

- **End-to-end latency targets:**
  - p50 ≤ 2 seconds.
  - p95 ≤ 4 seconds.
  - Hard ceiling: 6 seconds — above this, something is wrong, not just slow.
- **Per-stage latency budgets** (logged via `query_logs` latency fields already locked under storage):
  - Input filters (PII, out-of-scope patterns, no-performance patterns, query expansion): ≤50ms total.
  - Embedding API call (Voyage `voyage-finance-2`): ≤400ms.
  - Retrieval (Postgres semantic + lexical, RRF fusion): ≤100ms.
  - Reranking API call (Voyage `rerank-2`): ≤600ms.
  - LLM generation (Claude): ≤2.5s per call. Regeneration path adds another full LLM call.
  - Post-processing (citation verification, response shaping): ≤100ms.
  - Diagnostic queries flag turns exceeding any per-stage budget.
- **Cost targets:**
  - ≤ $0.05 per query in the normal flow.
  - ≤ $0.10 per query worst case (with regeneration).
  - Per-query cost logged in `query_logs.cost_usd` (locked under Storage).
  - Project-scale spend is not a real constraint, but tracking discipline is maintained.
- **"Added complexity gate" (documented in README):** any future layer (new retrieval stage, new judge, new verification pass) is justified only if:
  - Eval data shows the current pipeline fails on a specific mode the layer would fix.
  - The layer's latency stays inside the per-stage budget.
  - The layer's cost stays inside the per-query budget.
  - A simpler change (prompt tuning, threshold adjustment, dictionary update) wouldn't have produced the same lift.
- **Monitoring:** the scheduled operational health summary report (from diagnostic queries) is extended to include latency percentiles per stage and cost trends. No real-time alerts — visibility, not paging.
- **Escalation path when budgets are exceeded** (documented in README under "operational tuning"):
  - **Latency:** reduce hybrid retrieval candidates (20 → 10), switch to `rerank-2-lite`, evaluate lighter LLM for generation, defer regeneration, skip per-query citation verification under proven-stable conditions.
  - **Cost:** lighter model for retrievable tasks (e.g., out-of-scope classification), batch where possible, tighter prompt (fewer few-shot examples, leaner system prompt).
  - Not a feature to build now — guidance for when operational data shows budgets being exceeded.

### Backend Performance Dashboard (locked)

Logged operational data needs a place to be viewed. Otherwise tracking is theatre.

- **Tool: Metabase** (self-hosted via Docker), connecting directly to Postgres.
  - Free open-source version is sufficient.
  - Connects directly to Postgres — no new data pipeline needed; the operational data is already there.
  - Diagnostic queries from `diagnostics/` import as Metabase saved queries — no duplicated work.
- **Pre-built panels (~8 panels on a single dashboard view):**
  - **Performance:** latency overview (p50 / p95 / p99 trend, last 7/30 days, per-stage breakdown).
  - **Cost:** per-day cumulative cost trend.
  - **Quality summary:** thumbs-down rate, regeneration rate, invented-URL count, refusal-rate breakdown by refusal type (PII / out-of-scope / no-performance / thin-retrieval / mixed-query-refusal portion).
  - **Retrieval signals:** top retrieved sources (which chunks/sources are getting used most), top refused queries (clusters of patterns the bot can't handle).
  - **Session signals:** experience-level distribution (beginner / somewhat familiar / expert), session length distribution, post-chat document generation rate, mid-session experience-level change events.
  - **Recent thumbs-down drill-down:** the latest negative-feedback turns with one-click access to the full turn record (question, retrieved chunks, rerank order, final answer, citation, latency).
- **Ad-hoc queries:** Metabase's SQL editor handles exploratory queries against the same database. Same SQL skill, same data, no separate tool.
- **Refresh cadence:** live queries on page load. At project-scale query volume, Postgres handles dashboard queries in milliseconds. No caching infrastructure needed.
- **Access:**
  - Local-only deployment to start.
  - Metabase connects to Postgres via a dedicated **read-only DB role** — defense against accidental writes from the dashboard layer. Good discipline regardless of who's accessing.

---

## Summary — Decisions Cross-Reference

This section is a quick index back to the locked phases above. **The phase sections are the source of truth.** If anything below conflicts with a phase section, the phase section wins.

### What's IN (locked)

| Item | Phase | Decision |
|---|---|---|
| Project scope (ICICI Pru, 4 schemes, ~20 pages) | Phase 1 | Locked |
| Citation hierarchy | Phase 1 prelude | Locked |
| Document parsing (PyMuPDF + pdfplumber + Trafilatura + BeautifulSoup, markdown intermediate) | Phase 1 | Locked |
| Chunking (child 100–200 tokens, parent 600–800, structure-aware) | Phase 1 | Locked |
| Embeddings (Voyage `voyage-finance-2`, 1024 dims, metadata prepended) | Phase 1 | Locked |
| Storage (Postgres + pgvector, 8 tables with hybrid metadata typing) | Phase 1 | Locked |
| Hybrid retrieval (BM25 + semantic, RRF fusion, top 20) | Phase 2 | Locked |
| Filtering (pre-filter SQL, hard-coded scheme detection, latest-version default) | Phase 2 | Locked |
| Reranking (Voyage `rerank-2`, top 3 unique parents, swap after rerank) | Phase 2 | Locked |
| Parent retrieval (structural definition, self-parent fallback, metadata header) | Phase 2 | Locked |
| Query expansion (synonym dictionary, Option B hybrid) | Phase 2 | Locked |
| Grounding (hard threshold tuned via Phase 5 sweep, structured refusal) | Phase 2 | Locked |
| PII filter (regex pre-retrieval, hard refusal, content never logged) | Phase 3 | Locked |
| Out-of-scope refusal (6 enumerated categories, hybrid detection) | Phase 3 | Locked |
| No-performance-claims rule (3 sub-categories all refused, factsheet redirect) | Phase 3 | Locked |
| System prompt structure (static/dynamic split, 9 sections, 12 few-shots with conditional injection, Option B mixed queries) | Phase 3 | Locked |
| Answer length policy (quality + experience-level driven, runaway safety net, **brief's 3-sentence rule deliberately not honored**) | Phase 3 | Locked |
| Citation enforcement (end-of-answer line format, format/provenance checks, differentiated failure handling, `[FACTUAL]`/`[REFUSAL]` tag) | Phase 3 | Locked |
| Experience-level selector backend (3 buckets, default = somewhat_familiar, mutable via explicit command) | Phase 4 | Locked |
| Context reignition mechanics (structured facts + 5-turn window, dual-mode switching at ~5000 tokens) | Phase 4 | Locked |
| Selective warmth (per-level tone + affirming phrases, **no user name capture**, LLM-side detection with escalation path) | Phase 4 | Locked |
| Post-chat learnings document (on-demand, PDF, 6 sections, light reformatting with verbatim substantive content) | Phase 4 | Locked |
| Eval suite (implemented in this repo end-to-end) | Phase 5 | Locked |
| Diagnostic queries (~15–20 SQL files across 4 categories + thumbs-down family) | Phase 5 | Locked |
| Regulatory research output (3 categories of templates, 7-item research target, hybrid approach with manual review) | Phase 5 | Locked |
| Latency/cost budget thresholds (p50 ≤ 2s, p95 ≤ 4s, ≤ $0.05/query, added-complexity gate) | Phase 5 | Locked |
| Backend performance dashboard (Metabase, ~8 panels, local-only with read-only DB role) | Phase 5 | Locked |

### What's OUT (rejected, with reasoning in phase sections)

- HyDE / hypothetical questions — marginal benefit on a small corpus.
- Knowledge graph — overkill for corpus and question type.
- Multi-hop reasoning agent — not needed for single-fact lookups.
- CRAG (self-check before generation) — overkill at this scale.
- Cross-session memory / login system — no infrastructure for it; out of scope.
- User name capture — no login system, adds friction without value.
- LLM-based PII detection — closed list of formats, regex is sufficient.
- LLM-based scheme detection — closed list of 4 schemes, hard-coded list is sufficient.
- Hard sentence cap on answers — conflicts with experience-level design.
- Per-query LLM-as-judge citation alignment — too costly; handled via sample audit instead.
- Pre-built CI integration for evals — manual runs at this stage.
- Real-time alerts on operational metrics — operational-scale infrastructure, not project-scale.

### Deliberately Deferred (carved out for later)

- UI design (welcome screen, chat interface, suggested questions, mobile layout, disclaimer placement in UI).
- Summarization / context distillation of retrieved chunks — add only if prompts get crowded.
- Scheduled re-research of regulatory content — deferred to production scope.
- Cron jobs / change detection for document re-parsing — deferred to production scope.

### Brief Deliverables (still required)

- Working prototype.
- Source list CSV/MD of all URLs.
- README with scope, known limits, manual re-parsing procedure, annual regulatory review expectation, added-complexity gate, operational tuning escalation paths.
- Sample Q&A file.
- UI disclaimer snippet (UI itself deferred; the snippet wording itself comes from the regulatory templates).
