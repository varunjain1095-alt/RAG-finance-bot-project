"""Print full answers for answer-quality eval cases #1, #4, #12."""

import json
import os
import sys
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
from rag_bot.generation.logging_db import create_session
from rag_bot.generation.pipeline import ask

CASES = [
    (1, "What is the expense ratio of ICICI Prudential Flexicap Fund?"),
    (4, "What is the minimum SIP for Bluechip?"),
    (12, "What is Flexicap expense ratio and should I invest?"),
]


def main() -> int:
    reload_settings()
    out = []
    for case_id, query in CASES:
        session_id = create_session(experience_level="somewhat_familiar")
        result = ask(session_id, query)
        out.append(
            {
                "id": case_id,
                "query": query,
                "answer": result.answer,
                "cited_url": result.cited_url,
                "refusal_category": result.refusal_category,
            }
        )
        print(f"\n{'='*60}\nCASE #{case_id}\nQuery: {query}\n")
        print(result.answer)
        print(f"\ncited_url: {result.cited_url}")
        print(f"refusal_category: {result.refusal_category}")

    (PROJECT_ROOT / "evals" / "results" / "answer_quality_samples.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
