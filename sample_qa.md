"""Representative passing Q&A for graders and manual smoke tests."""

# Sample Q&A — ICICI Prudential RAG FAQ Bot

Curated factual questions with expected behavior. Answers depend on ingested corpus; verify against live `/chat` after ingest.

| # | Question | Expected behavior |
|---|----------|-------------------|
| 1 | What is the expense ratio of ICICI Prudential Flexicap Fund? | Factual answer with factsheet citation; scheme filter applied |
| 2 | What is the exit load for ELSS Tax Saver? | Factual answer; ELSS scheme detected |
| 3 | What is expense ratio? | General concept; AMFI or scheme source per citation hierarchy |
| 4 | What is the minimum SIP for Bluechip? | Factual; Large Cap / Bluechip variant detected |
| 5 | What is the lock-in period for ELSS? | Factual 3-year lock-in from KIM/factsheet |
| 6 | What is the riskometer for Balanced Advantage Fund? | Factual scheme attribute with citation |
| 7 | What about its exit load? (after Q1 about Flexicap) | Multi-turn; resolves "its" via session state |
| 8 | Should I buy Bluechip? | Out-of-scope refusal; no retrieval |
| 9 | What is the 5-year CAGR of Bluechip? | No-performance refusal; factsheet redirect |
| 10 | My PAN is ABCDE1234F | PII refusal; content not stored |
| 11 | explain simpler | Experience level switches to `new`; acknowledgment |
| 12 | What is Flexicap expense ratio and should I invest? | Mixed: factual part + advisory decline |

## CLI demo path

```bash
set PYTHONPATH=src
docker compose up -d postgres
python scripts/apply_migrations.py
python scripts/ingest.py   # if corpus not loaded

# Session + chat
curl -X POST http://127.0.0.1:8000/session -H "Content-Type: application/json" -d "{\"experience_level\":\"somewhat_familiar\"}"
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d "{\"session_id\":\"<id>\",\"message\":\"What is Flexicap expense ratio?\"}"

# Learnings PDF
curl -O http://127.0.0.1:8000/learnings/<session_id>
```

## Retrieval-only debug

```bash
python scripts/retrieve.py "What is the exit load for ELSS?"
```
