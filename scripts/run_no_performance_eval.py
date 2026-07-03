"""Run 5.2.4 no-performance live eval only."""

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
from rag_bot.evals.runner import eval_no_performance


def main() -> int:
    reload_settings()
    result = eval_no_performance()
    print(f"5.2.4_no_performance: {result['passed']}/{result['total']} passed")
    for case in result.get("cases", []):
        if not case["passed"]:
            print(f"  FAIL: {case['query']} — {case['detail']}")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
