# Eval suite brief (Phase 5.2)

Run the eval suite in this repo (Cursor). Inputs are locked in `context.md`, `evals.md`, and the paths below.

## Scope

Generate, run, and store results for:

1. Scheme detector eval (`retrieval/schemes.py` hard-coded list)
2. Query expansion eval (semantic always-expand; lexical conditional)
3. Out-of-scope detector eval (rule patterns + LLM layer in prompt)
4. No-performance detector eval
5. Selective warmth eval (per experience level instructions)
6. **Grounding threshold sweep** — balance false-refusal vs hallucination; **commit winning threshold to `GROUNDING_THRESHOLD` in `.env`**
7. Citation consistency eval (same question → same citation)
8. Source overlap eval (multi-document facts)
9. Answer-quality eval on `sample_qa.md` questions
10. Regulatory verbatim verification (`templates/regulatory/`, `templates/ui_disclaimer_snippet.md`, performance refusals, learnings disclaimer)

## Pass/fail sources

- Per-scenario criteria in `evals.md` (IDs `P2-*`, `P3-*`, `P4-*`, `P5-*`)
- Phase gates in `evals.md` summary tables

## Grounding threshold deliverable

Run sweep on ingested corpus with live retrieval. Report:

- False-refusal rate on in-scope factual set
- Hallucination rate on sample audit
- Recommended `GROUNDING_THRESHOLD` value

Integrate result into project config; document in README.

## Regulatory verbatim eval

Programmatic checks that mandatory disclaimer strings from `templates/regulatory/mandatory_disclaimers.md` appear **verbatim** in:

- `templates/ui_disclaimer_snippet.md`
- `templates/learnings_document_disclaimer.md`
- `no_performance_refusal_message()` output (via `tests/test_regulatory_templates.py`)

## Out of scope for automated eval runs

- Metabase dashboard (manual setup per `diagnostics/METABASE_SETUP.md`)
- Diagnostic SQL authoring (already in `diagnostics/`)

## Repository eval inputs

| Asset | Path |
|-------|------|
| Locked decisions | `context.md` |
| Scenario catalog | `evals.md` |
| Sample questions | `sample_qa.md` |
| Edge cases | `edge-case.md` |
| Ingestion report | `ingestion_report.md` |

Deliver eval results as markdown summary + machine-readable JSON in `evals/results/`.
