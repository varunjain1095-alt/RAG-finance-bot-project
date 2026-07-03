"""Run Phase 5.2 live eval suite against the real ask()/retrieve() pipeline."""

from __future__ import annotations

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

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rag_bot.config import reload_settings
from rag_bot.evals.runner import run_eval_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5.2 live eval suite")
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip evals that require Anthropic API (warmth, citations, answer quality)",
    )
    parser.add_argument(
        "--no-apply-threshold",
        action="store_true",
        help="Run grounding sweep but do not write GROUNDING_THRESHOLD to .env",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full summary JSON to stdout",
    )
    args = parser.parse_args()

    reload_settings()
    results = run_eval_suite(
        apply_threshold=not args.no_apply_threshold,
        skip_llm=args.skip_llm,
    )

    agg = results["aggregate"]
    print(
        f"Eval suite complete: {agg['passed']}/{agg['total']} passed "
        f"({agg['pass_rate']:.1%})"
    )
    print(f"GROUNDING_THRESHOLD: {results.get('final_grounding_threshold')}")
    print(f"Results written to {PROJECT_ROOT / 'evals' / 'results'}")

    for name, ev in results["evals"].items():
        if ev.get("skipped"):
            print(f"  {name}: SKIPPED ({ev.get('reason', '')})")
        else:
            print(
                f"  {name}: {ev.get('passed', 0)}/{ev.get('total', 0)} passed"
            )

    if args.json:
        print(json.dumps(results, indent=2, default=str))

    return 0 if agg["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
