"""Run Phase 2 retrieval harness."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRESERVE_ENV_KEYS = (
    "DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "VOYAGE_API_KEY",
    "ANTHROPIC_MODEL",
    "GROUNDING_THRESHOLD",
)
_preserved_env = {key: os.environ[key] for key in _PRESERVE_ENV_KEYS if os.environ.get(key)}
load_dotenv(PROJECT_ROOT / ".env", override=True)
for key, value in _preserved_env.items():
    os.environ[key] = value

from rag_bot.config import reload_settings
from rag_bot.retrieval.pipeline import retrieve
from rag_bot.retrieval.types import RetrievalOutcome


def _format_result(result) -> str:
    lines = [
        f"outcome: {result.outcome.value}",
        f"query: {result.query}",
    ]
    if result.detected_scheme:
        lines.append(f"scheme_filter: {result.detected_scheme}")
    if result.top_rerank_score is not None:
        lines.append(f"top_rerank_score: {result.top_rerank_score:.4f}")
    lines.append(f"rerank_used: {result.rerank_used}")
    lines.append(
        "timing_ms: "
        + json.dumps(
            {
                "scheme_detection": round(result.timing.scheme_detection, 1),
                "expansion": round(result.timing.expansion, 1),
                "embed": round(result.timing.embed, 1),
                "retrieval": round(result.timing.retrieval, 1),
                "rerank": round(result.timing.rerank, 1),
                "assembly": round(result.timing.assembly, 1),
                "total": round(result.timing.total, 1),
            }
        )
    )
    if result.message:
        lines.append("")
        lines.append(result.message)
    if result.parents:
        lines.append("")
        lines.append(f"--- top {len(result.parents)} parents ---")
        for i, parent in enumerate(result.parents, 1):
            score = parent.rerank_score
            score_str = f"{score:.4f}" if score is not None else "rrf-only"
            lines.append(f"[{i}] score={score_str} parent_id={parent.parent_chunk_id}")
            preview = parent.formatted_text[:400].replace("\n", " ")
            lines.append(f"    {preview}...")
    if result.debug:
        lines.append("")
        lines.append("debug: " + json.dumps(result.debug))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 retrieval harness")
    parser.add_argument("query", help="User query text")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of human-readable output",
    )
    args = parser.parse_args()

    reload_settings()
    result = retrieve(args.query)

    if args.json:
        payload = {
            "outcome": result.outcome.value,
            "query": result.query,
            "detected_scheme": result.detected_scheme,
            "top_rerank_score": result.top_rerank_score,
            "rerank_used": result.rerank_used,
            "message": result.message,
            "timing_ms": {
                "scheme_detection": result.timing.scheme_detection,
                "expansion": result.timing.expansion,
                "embed": result.timing.embed,
                "retrieval": result.timing.retrieval,
                "rerank": result.timing.rerank,
                "assembly": result.timing.assembly,
                "total": result.timing.total,
            },
            "parents": [
                {
                    "parent_chunk_id": p.parent_chunk_id,
                    "source_name": p.source_name,
                    "source_url": p.source_url,
                    "date_version": p.date_version,
                    "rerank_score": p.rerank_score,
                    "formatted_text": p.formatted_text,
                }
                for p in result.parents
            ],
            "debug": result.debug,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_format_result(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
