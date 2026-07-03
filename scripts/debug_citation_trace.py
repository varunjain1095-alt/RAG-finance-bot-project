"""Trace citation path for Flexicap vs ELSS expense/exit-load queries."""

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRESERVE = (
    "DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "VOYAGE_API_KEY",
    "ANTHROPIC_MODEL",
    "GROUNDING_THRESHOLD",
)
_preserved = {k: os.environ[k] for k in _PRESERVE if os.environ.get(k)}
load_dotenv(PROJECT_ROOT / ".env", override=True)
for k, v in _preserved.items():
    os.environ[k] = v

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rag_bot.config import reload_settings
from rag_bot.generation.citations import enforce_citation, parse_citation_block
from rag_bot.generation.logging_db import create_session
from rag_bot.generation.pipeline import ask
from rag_bot.retrieval.pipeline import retrieve


def trace_query(label: str, query: str) -> dict:
    reload_settings()
    retrieval = retrieve(query)
    parent_info = [
        {
            "parent_chunk_id": p.parent_chunk_id,
            "source_name": p.source_name,
            "source_url": p.source_url,
            "date_version": p.date_version,
            "scheme_name": p.scheme_name,
            "header_preview": p.formatted_text.split("\n", 1)[0],
        }
        for p in retrieval.parents
    ]
    session_id = create_session(experience_level="somewhat_familiar")
    result = ask(session_id, query)
    raw = result.answer if result.citation_flow.final_outcome == "fallback_refusal" else result.answer
    parsed = parse_citation_block(result.answer)
    parsed_raw = parse_citation_block(result.answer)
    return {
        "label": label,
        "query": query,
        "retrieval_outcome": retrieval.outcome.value,
        "detected_scheme": retrieval.detected_scheme,
        "top_rerank_score": retrieval.top_rerank_score,
        "parents": parent_info,
        "cited_url": result.cited_url,
        "citation_flow": result.citation_flow.to_dict() if result.citation_flow else None,
        "refusal_category": result.refusal_category,
        "parsed_citation_url": parsed_raw.citation_url,
        "parsed_from_answer": parsed.citation_url,
        "answer_preview": result.answer[:500],
    }


def main() -> int:
    cases = [
        (
            "flexicap",
            "What's the expense ratio of Flexicap Fund?",
        ),
        (
            "flexicap_eval",
            "What is the expense ratio of ICICI Prudential Flexicap Fund?",
        ),
        (
            "elss",
            "What is the exit load for ELSS Tax Saver?",
        ),
    ]
    reports = [trace_query(label, q) for label, q in cases]
    out = PROJECT_ROOT / "evals" / "results" / "citation_debug.json"
    out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    for r in reports:
        print(f"\n=== {r['label']} ===")
        print(f"outcome={r['retrieval_outcome']} cited_url={r['cited_url']}")
        print(f"citation_flow={r['citation_flow']}")
        print(f"parsed_from_answer={r['parsed_from_answer']}")
        for i, p in enumerate(r["parents"], 1):
            print(f"  parent[{i}] url={p['source_url']}")
        print(f"answer_preview: {r['answer_preview'][:300]}...")
    print(f"\nWritten {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
