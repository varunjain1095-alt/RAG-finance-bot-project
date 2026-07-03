# Interview Script — ICICI Prudential RAG FAQ Bot

Use this as a spoken guide, not a word-for-word script. Pick the **30s / 2min / 5min** version based on time, then go deeper only if they ask.

---

## 30-second elevator pitch

> I built a **production-style RAG chatbot** for ICICI Prudential mutual fund FAQs — four schemes, ~13 authoritative sources, facts only, no investment advice. It ingests PDFs and HTML into PostgreSQL with pgvector, retrieves with **BM25 + semantic search + reranking**, generates with **Claude**, and **programmatically enforces citations** so every factual answer links to a real source URL. I also added session memory, experience levels for beginners vs experts, multi-turn serial explainers for broad topics like “what is a mutual fund,” operational diagnostics, and a demo UI embedded in an INDmoney-style host app.

---

## 2-minute story arc

**Setup (15s)**  
> The problem is deceptively hard: users ask casual finance questions, but the bot must only state **verifiable facts** from official documents — expense ratios, exit loads, lock-ins — and **refuse** advice, performance claims, and PII. Wrong answers in this domain erode trust fast.

**What I built (45s)**  
> End-to-end pipeline: **ingest → chunk → embed → retrieve → generate → verify → log**.  
> - **Ingestion:** PyMuPDF + pdfplumber for PDFs, Trafilatura for HTML → markdown → parent/child chunks (600–800 / 100–200 tokens).  
> - **Retrieval:** Hybrid search in Postgres (pgvector + full-text), RRF fusion, Voyage rerank, top 3 parent chunks to the LLM. Scheme detection pre-filters queries to the right fund.  
> - **Generation:** Layered input filters (PII, out-of-scope, no-performance) *before* any LLM call; grounding threshold skips generation when retrieval is weak.  
> - **Trust layer:** Citation format + URL provenance checked in code; one regeneration if the model hallucinates a link.

**Differentiators (30s)**  
> This isn’t “prompt and pray.” Refusals for advisory questions are **static templates** (no LLM spend). Experience level (`new` / `somewhat familiar` / `expert`) changes tone and few-shots. For broad questions, **serial explanation mode** delivers one section at a time with a programmatic `offer_next` closing — like a guided tutorial, not a wall of text.

**Outcome / ops (30s)**  
> Every turn logs latency breakdown, cost, retrieval context, and citation flow to `query_logs`. I wrote **17+ diagnostic SQL queries**, a health report CLI, Metabase dashboard setup, and a live eval suite. I also optimized serial turns from ~2 LLM calls / ~9s down to **1 call / ~3s** by trimming prompt sources and enforcing closings in code instead of regenerating.

---

## 5-minute technical walkthrough (whiteboard order)

### 1. Scope boundary (30s)

> **In scope:** ICICI Pru — Bluechip, Flexicap, ELSS, Balanced Advantage. Facts from factsheets, KIMs, AMFI, SEBI, AMC pages.  
> **Out of scope:** “Should I buy?”, returns/CAGR, PII, cross-session memory, other AMCs.

*If they push:* “I locked scope in a `context.md` file so every design choice traces back to written decisions — useful when course briefs and generic RAG tutorials disagree.”

### 2. Data pipeline (60s)

```
Sources (PDF/HTML) → parse to markdown → parent/child chunks → BGE embeddings (768d, local)
                  → PostgreSQL (source_documents, parent_chunks, child_chunks)
```

> Parents give the LLM readable context; children give retrieval precision. Metadata — scheme name, source type, URL, date — is filterable and drives **citation hierarchy** (factsheet for TER, KIM for exit load, AMFI for general concepts).

*Talking point:* “I generate an `ingestion_report.md` after every ingest so I know which documents parsed cleanly before I trust answers.”

### 3. Retrieval (60s)

```
Query → scheme detector → query expansion (synonym dict)
     → semantic (pgvector) + lexical (BM25) → RRF (k=60) → top 20
     → Voyage rerank-2 → dedupe by parent → top 3 parents
     → grounding check (rerank score threshold)
```

> If the top score is below threshold, **no LLM call** — structured refusal with links to official sources. Rerank fails open to RRF order so the system still works if Voyage is down.

*Example:* “User says ‘Bluechip annual fee’ — expansion maps to expense ratio; scheme filter locks to Large Cap fund; citation picks factsheet URL.”

### 4. Generation & safety (90s)

**Order of operations (important — shows systems thinking):**

1. PII regex → hard stop, log event, never store raw PII  
2. Out-of-scope / performance patterns → static refusal  
3. Retrieve + ground  
4. Assemble prompt: static system rules → experience instructions → 4 level-matched few-shots → conversation state → sources → question  
5. Claude generates `[FACTUAL]` answer + citation lines  
6. **Post-processing:** runaway guard, citation enforcement, serial section enforcement  

> Mixed queries (“What’s the expense ratio and should I invest?”) answer the factual half with citation and refuse the advisory half — logged as `mixed_factual_advisory`.

### 5. Product features (60s)

| Feature | One-liner |
|--------|-----------|
| Experience level | Prompt + few-shots switch; user picks New / Somewhat familiar / Expert after first question |
| Context reignition | Structured session state + 5-turn window; turn embeddings for long sessions |
| Serial explanations | “Explain mutual funds” → section 1 only + “Would you like me to run through the key mechanics?” |
| Clarification | “I don’t get it” re-explains last section without fresh junk retrieval |
| Learnings PDF | On-demand summary of facts learned + transcript + sources |
| Demo UI | INDmoney US Stocks host shell + floating chat FAB wired to FastAPI |

### 6. Observability (30s)

> `query_logs` stores `final_prompt`, `citation_flow` JSON, per-stage `latency_*_ms`, and `cost_usd`. Thumbs-down flows into SQL diagnostics. Chat errors categorized: `embedding_retrieval`, `database`, `llm_generation`, `unexpected`.

---

## STAR stories (behavioral + depth)

### Story 1 — Citation hallucination

**Situation:** Model sometimes cited plausible-looking URLs not in retrieved chunks.  
**Task:** Brief requires one verifiable link per factual answer.  
**Action:** Built programmatic verifier — regex format check + URL must exist in retrieved set; one regen; fallback refusal with hierarchy-based link if still wrong. Log `citation_flow` for every turn.  
**Result:** Invented URLs are caught before the user sees them; diagnostics SQL counts `invented_url` failures.

### Story 2 — Serial explanation runaway + latency

**Situation:** “What is a mutual fund?” at New level returned all sections at once or needed a second LLM call (~8s generation).  
**Task:** Deliver one section per turn with `offer_next`, keep latency reasonable.  
**Action:** (1) Serial prompt block above retrieved sources, (2) sentence-level scope filter for later-section content, (3) programmatic `ensure_serial_closing`, (4) trim prompt to top-1 parent for serial turns while keeping full parent pool for citation, (5) forbidden-topic instructions per section.  
**Result:** 2 API calls → 1; generation ~8.5s → ~2.2s; `offer_next` and AMFI citation preserved.

### Story 3 — “I don’t get it” mid-conversation

**Situation:** User confused after SIP section; bot re-retrieved unrelated PDF pages and cited wrong source.  
**Task:** Treat clarification as re-explain, not new retrieval.  
**Action:** Clarification intent router before serial abort; low-confidence citation guard at grounding threshold + margin.  
**Result:** Re-explains prior section from stored parents; borderline rerank scores get honest “couldn’t find clear answer” instead of confident wrong citation.

### Story 4 — Added-complexity gate

**Situation:** Easy to add judges, extra retrieval stages, or streaming.  
**Task:** Stay within latency/cost budgets (p50 ≤ 2s target, $0.05/query).  
**Action:** Documented gate in README — new layer only if eval proves failure mode, fits budget, and simpler fix won’t work. Rolled back streaming when it added complexity without UX win.  
**Result:** Kept architecture auditable; invested in logging and programmatic enforcement instead of more LLM calls.

---

## Demo script (live or recorded — ~3 minutes)

1. **Open host UI** — “This simulates INDmoney’s US Stocks tab; the green FAB opens the FAQ bot — only intentional addition.”
2. **First message:** `what is a mutual fund` → experience prompt → select **New**.
3. **Point out:** Single section answer, plain language, **offer_next** question, AMFI citation with date.
4. **Continue:** “Yes” or “key mechanics” → section 2 only.
5. **Scheme lookup:** `What is the expense ratio for Flexicap?` → scheme filter, concise factual line, factsheet citation.
6. **Refusal:** `Should I invest in ELSS?` → no retrieval; advisory refusal + redirect.
7. **Ops (optional):** Show `query_logs` row or `python scripts/diag.py thumbs_down_review` — “Every turn is debuggable.”

---

## “Hardest part” answers (pick one)

**Option A — Trust in finance**  
> Generic RAG assumes the model will stay grounded. Here, grounding threshold + citation enforcement + no-performance rule are **first-class pipeline stages**, not prompt footnotes.

**Option B — Scope vs helpfulness**  
> Users ask advisory questions constantly. Separating factual intent from advisory intent — and handling mixed queries — without frustrating users required layered filters plus careful refusal copy.

**Option C — Evaluation without production traffic**  
> Built a live eval suite against real `/chat` with 10 scenario groups (scheme detection, expansion, refusals, warmth, grounding sweep, citation consistency) because unit tests alone don’t catch retrieval drift.

---

## Trade-offs I can defend

| Decision | Why |
|----------|-----|
| Local BGE embeddings vs Voyage embed | Cost/latency at ingest; rerank still Voyage finance-tuned |
| Programmatic citation vs LLM-as-judge | Deterministic, fast, auditable; alignment sampled in evals |
| Static refusals for obvious advisory | Zero LLM cost, consistent compliance messaging |
| Parent/child chunks | Small chunks retrieve well; parents give LLM coherent context |
| 24h session expiry | No cross-session memory by design; stale state misleads |
| Serial regen → programmatic enforcement | Latency and cost; model inconsistency handled in code |

---

## Questions to ask them (shows seniority)

- “How do you handle ** citation grounding** in regulated domains today?”
- “Where’s the line between **retrieval confidence** and **generation** in your stack?”
- “Do you log **full prompts** in prod, or sampled — and how do you debug thumbs-down?”

---

## Closing line

> I treated this as a **small production system**, not a notebook demo: locked architecture docs, explicit refusal boundaries, enforced citations, structured logging, and evals. I’m most proud of the **trust layer** — the bot is useful because it knows when *not* to answer, and when it does, you can click the source and verify it.

---

## Quick reference — stack

| Layer | Choice |
|-------|--------|
| API | FastAPI |
| DB | PostgreSQL + pgvector |
| Parse | PyMuPDF, pdfplumber, Trafilatura, BeautifulSoup |
| Embed | BGE-base-en-v1.5 (local, 768d) |
| Rerank | Voyage rerank-2 |
| LLM | Claude (Haiku for dev/eval, Sonnet configurable) |
| UI | Vanilla HTML/CSS/JS host + chat overlay |
| Ops | Metabase, diagnostic SQL, eval runner |

---

## If they only ask one thing

> **“Walk me through one query end-to-end.”**  
> Use the Flexicap expense ratio example from the demo script and narrate each pipeline stage through to `query_logs`.
