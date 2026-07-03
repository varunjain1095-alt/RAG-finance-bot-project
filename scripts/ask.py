"""Run Phase 3 ask pipeline."""

import argparse
import json
import os
import sys
import uuid
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
from rag_bot.generation.logging_db import create_session
from rag_bot.generation.pipeline import ask


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 ask CLI")
    parser.add_argument("question", help="User question")
    parser.add_argument("--session-id", help="Existing session UUID")
    parser.add_argument(
        "--experience-level",
        choices=["new", "somewhat_familiar", "expert"],
        default="somewhat_familiar",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    reload_settings()
    session_id = uuid.UUID(args.session_id) if args.session_id else create_session(
        experience_level=args.experience_level
    )
    result = ask(session_id, args.question)

    if args.json:
        print(
            json.dumps(
                {
                    "turn_id": str(result.turn_id),
                    "session_id": str(result.session_id),
                    "answer": result.answer,
                    "refusal_category": result.refusal_category,
                    "cited_url": result.cited_url,
                    "cost_usd": result.cost_usd,
                    "timings_ms": {
                        "input_filters": result.timings.input_filters_ms,
                        "embedding": result.timings.embedding_ms,
                        "retrieval": result.timings.retrieval_ms,
                        "rerank": result.timings.rerank_ms,
                        "generation": result.timings.generation_ms,
                        "postprocessing": result.timings.postprocessing_ms,
                        "total": result.timings.total_ms,
                    },
                },
                indent=2,
            )
        )
    else:
        print(f"session_id: {result.session_id}")
        print(f"turn_id: {result.turn_id}")
        if result.refusal_category:
            print(f"refusal_category: {result.refusal_category}")
        print()
        print(result.answer)

    return 0


if __name__ == "__main__":
    sys.exit(main())
