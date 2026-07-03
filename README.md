# RAG finance bot project

A RAG-based intelligent assistant built on INDmoney's platform

A production-grade, facts-only conversational assistant that answers questions about ICICI Prudential mutual fund schemes using retrieved official sources. Built as part of the Next Leap LIP program.


What this project is

This is not a simple FAQ chatbot. It is a full retrieval-augmented generation (RAG) pipeline with a grounded, citation-enforced generation layer, multi-turn guided explanations, session-aware personalization, and a post-conversation learning artifact. Every answer is sourced, every claim is cited, and the system is explicitly designed to refuse investment advice.


Scope

AMC: ICICI Prudential Asset Management Company

Schemes covered:


ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund)
ICICI Prudential Flexicap Fund
ICICI Prudential ELSS Tax Saver Fund
ICICI Prudential Balanced Advantage Fund


Corpus: 13 ingested sources including scheme factsheets, the AMC's combined monthly factsheet PDF, TER disclosure data for June 2026, AMFI investor education pages, the SEBI Investor Charter, scheme-level FAQ content, and CAMS registrar references.


Architecture

Phase 1: Ingestion pipeline

Documents are parsed using PyMuPDF and pdfplumber for PDFs (with Tesseract OCR fallback for scanned pages) and Trafilatura with BeautifulSoup fallback for HTML. The pipeline normalizes all content to markdown as an intermediate format before chunking.

Chunking uses a parent-child structure: small child chunks (100-200 tokens) are embedded and searched for precision, while larger parent chunks (600-800 tokens) are swapped in at generation time for context. Structure-aware splitting is used where document structure permits, with recursive character splitting as a fallback. Metadata attached per chunk includes source name, source type, source URL, date/version, scheme name, section heading, parent chunk ID, and authority level.

Embedding uses Voyage AI voyage-finance-2, a finance-domain-tuned model, running at 1024 dimensions. All embeddings are stored in PostgreSQL with the pgvector extension. A BGE bge-base-en-v1.5 local model (768 dimensions) handles runtime inference, stored in data/models/ to avoid dependency on Hugging Face's hub at query time.

The database schema spans eight tables: source_documents, parent_chunks, child_chunks, sessions, query_logs, feedback, pii_refusals, and session_turn_embeddings. Document versioning is tracked per source URL so re-ingesting an updated factsheet correctly demotes the prior version without deleting historical data.

Phase 2: Retrieval pipeline

Hybrid retrieval combines semantic vector search (pgvector cosine similarity) with lexical BM25 search (Postgres full-text search), fused via Reciprocal Rank Fusion with k=60. The top 20 candidates from each search are merged to a top 20 list before reranking.

Reranking uses Voyage AI rerank-2 to score each candidate against the query in context. The top 3 unique parents are selected after deduplication by parent chunk ID, with the highest-ranked child per parent determining the order.

Filtering is pre-retrieval, applied via SQL WHERE clauses. Scheme detection uses a hardcoded synonym map (e.g. "Bluechip", "erstwhile Bluechip" both route to the Large Cap fund). Authority level filtering follows a citation hierarchy: factsheets are preferred for scheme-specific numbers, KIMs for scheme rules, AMFI for general concepts, SEBI for regulatory content, and CAMS for statement-download questions.

Query expansion uses a synonym dictionary bridging user language to document language (e.g. "annual fee" to "expense ratio", "withdrawal" to "redemption"). Semantic search always expands; lexical search expands conditionally when a user-side synonym is detected.

A hard grounding threshold gates generation: if the top reranker score falls below the threshold, the pipeline returns a thin-retrieval refusal rather than hallucinating. When no reranker score is available (fallback to RRF order), the semantic similarity score is used instead. If no score exists at all, the response defaults to a refusal.

Phase 3: Generation pipeline

Input filters run in sequence before any retrieval: PII detection (regex for PAN, Aadhaar, account numbers, OTPs, emails, and Indian phone numbers), out-of-scope detection (investment advice, portfolio recommendations, performance predictions, and personal finance questions), no-performance-claims detection (returns, CAGR, benchmarks comparisons), and investment recommendation detection ("what is the best fund to invest in" style queries).

The system prompt is assembled dynamically with a static block (identity, scope rules, grounding instructions, citation format, answer format guidelines) and a dynamic block (experience-level instructions, relevant conversation state, retrieved sources with metadata headers, and the current question). Four few-shot examples are injected per query, selected from a 12-example library (4 categories x 3 experience levels) based on the current session's level.

Citation enforcement is programmatic: every answer must include a Source: line with a URL that matches the retrieved sources. On failure, the pipeline regenerates once with a stricter instruction, then falls back to a structured refusal. Citation URLs for TER data route to ICICI Prudential's official TER disclosure page, not the combined factsheet PDF.

A runaway safety net catches pathologically long answers (approximately 250 words or 8 sentences for factual answers, with tighter caps for serial-explanation sections). This does not apply a hard sentence count across the board: answer length is quality and experience-level driven.

Mixed factual-plus-advisory queries are handled by answering the factual portion with citation and declining the advisory portion with a redirect, in the same response.

Phase 4: Session and product layer

Context reignition stores structured session state (schemes discussed, refusals encountered, experience level, explicit preferences) plus a rolling 5-turn verbatim window. When state crosses approximately 5000 tokens, the system switches from load-whole to retrieval mode, embedding past turns with the same BGE model and performing a session-scoped pgvector lookup per new query.

Experience-level selection (New / Somewhat familiar / Expert) is presented only when the user asks a broad conceptual question that triggers the serial-explanation path. Factual lookups skip the experience prompt entirely and use the session default. The experience question text is "How familiar are you with financial products and investing?" and the selection is reused across the session without re-prompting.

Selective warmth is applied per experience level: encouraging and parenthetical for New, neutral for Somewhat familiar, terse for Expert. Warmth is tied to the user's curiosity, never their investment decisions, and never uses the user's name since there is no login system.

The post-chat learnings PDF is generated on demand using fpdf2 after the user's second message in a session, triggered by a small inline prompt in the chat. The PDF contains six sections: a brief disclaimer, key facts (LLM-extracted with numeric overlap sanity check), conversation transcript, sources referenced, what was not covered, and the full regulatory disclaimer. Server-side retention is approximately one hour; the user's downloaded copy is the persistent artifact.

Phase 5: Operations

Sixteen parameterized SQL diagnostic queries span four categories (retrieval, reranking, generation, citation) plus thumbs-down review and an operational health rollup. A CLI wrapper (scripts/diag.py) provides convenient access. Metabase connects via a read-only Postgres role to provide live dashboards covering latency percentiles, cost trends, quality signals, and session patterns.

Regulatory templates sourced from SEBI and AMFI cover the mandatory market-risk disclaimer, scope statements, authoritative redirect links, grievance redressal references, and SEBI-registered advisor referral language. All templates were manually reviewed for verbatim accuracy before shipping.


Advanced features

Serial guided explanations: Broad conceptual questions ("explain mutual funds", "what is SIP") trigger a section-by-section guided flow. The first section is delivered with a closing offer ("Would you like me to run through the key mechanics?"). Each section has programmatic scope enforcement: sentences containing content from later sections are filtered before any regeneration attempt. The offer-to-continue line is appended programmatically if the model omits it, eliminating an entire LLM regeneration round trip. After the final section, the bot surfaces three related topics from the corpus. This feature reduced latency on serial-mode turns from approximately 9.6 seconds (two LLM calls) to 3.45 seconds (one LLM call) after prompt trimming and post-processing reordering.

Clarification handling: "I don't get it" and similar confusion phrases mid-conversation re-explain the current serial section in simpler language without aborting the flow or triggering a fresh retrieval. A separate borderline-grounding guard ensures that low-confidence results (reranker score near the threshold) never receive a confident wrong citation; they instead return an honest thin-retrieval response.

Accessibility menu: A persistent accessibility button in the chat header provides in-app zoom/text-size control and theme switching between Light, Dark Navy, and True Black. This is in addition to OS-level accessibility support.

Scheme-name resilience: The scheme detector maps common variants and misspellings to the correct canonical scheme. A general grounding rule handles AMC renames ("Bluechip Fund is now called Large Cap Fund") by surfacing the current name from the ingested source documents rather than requiring spec updates when fund names change.

Error categorization and startup health check: Every /chat failure is categorized (embedding/retrieval, database, LLM generation, or unexpected) and logged with a full traceback before returning a generic error to the user. The BGE embedding model is verified at server startup before traffic is accepted; a corrupted model cache fails loudly at boot rather than silently on the first chat request.


Setup

Requirements: Python 3.11+, Miniconda or Anaconda, Docker Desktop.

Environment variables (copy .env.example to .env):


ANTHROPIC_API_KEY: Claude API key (used for generation, learnings PDF extraction)
VOYAGE_API_KEY: Voyage AI key (used for reranking via rerank-2)
DATABASE_URL: Postgres connection string (default: postgresql://rag:rag@localhost:5433/rag_bot)
ANTHROPIC_MODEL: Claude model string (default: claude-sonnet-4-6)


Starting the database:

docker compose up -d postgres

Installing dependencies (first time only):

conda activate rag-bot
pip install -e .

Running ingestion:

python scripts/ingest.py

Starting the API and UI:

uvicorn rag_bot.main:app --reload --app-dir src --host 0.0.0.0 --port 8000

Open http://localhost:8000/ui/ in a browser.

Running diagnostics:

python scripts/diag.py list
python scripts/diag.py thumbs_down_review --days 14
python scripts/operational_health_report.py


Known limitations

The following are documented, deliberate scope decisions rather than bugs:


KIM documents for Large Cap, ELSS Tax Saver, and Balanced Advantage funds were not located due to the AMC's JavaScript-rendered downloads hub; factsheets provide fallback coverage for the same fact types.
Four ICICI Pru investor-services pages (statements hub, capital gains, account statement, help center) returned 404; CAMS registrar pages cover the statement-download question category.
Four scheme-detail pages (the marketing/overview pages for each scheme) return no extractable text due to JavaScript rendering; all factual content for these schemes is covered by factsheets and the TER disclosure data.
Scheme pages are not ingested; all scheme-specific facts come from factsheets, KIM (Flexicap only), and the TER CSV.
The bot does not retain state across sessions; each new session starts fresh.
Performance figures (returns, CAGR, NAV history) are explicitly excluded per the no-performance-claims policy.



Operational notes

Re-ingestion: if a factsheet is updated, run python scripts/ingest.py again with the updated source in source_list.md. The versioning system will demote the prior document version and ingest the new one. Recommend reviewing ingestion_report.md after every re-ingest.

Regulatory review: regulatory templates in templates/regulatory/ should be reviewed annually or when SEBI or AMFI announce material changes to investor communication requirements.

Latency tuning: if response times degrade, the primary levers are reducing the number of serial-mode retrieved sources (currently top-1 parent for generation, full set retained for citation), switching to a lighter model for non-serial factual queries, or reducing the few-shot injection from 4 to 2 examples. Do not add new pipeline layers without confirming measurable improvement against the eval suite (python scripts/run_eval_suite.py).

Grounding threshold: the current production value is 0.35. Adjust GROUNDING_THRESHOLD in .env and validate with python scripts/run_grounding_sweep.py before changing in production.


Brief deliverables


Working prototype: http://localhost:8000/ui/ after following setup above
Source list: source_list.md
Sample Q&A: sample_qa.md
UI disclaimer snippet: templates/ui_disclaimer_snippet.md
Ingestion report: regenerated at ingestion_report.md on each ingest run
