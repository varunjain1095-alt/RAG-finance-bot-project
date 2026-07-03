"""Re-run grounding threshold sweep and update .env only."""

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

from rag_bot.config import get_settings, reload_settings
from rag_bot.evals.runner import eval_grounding_sweep, update_env_grounding_threshold


def main() -> int:
    reload_settings()
    sweep = eval_grounding_sweep()
    recommended = float(sweep["recommended_threshold"])
    update_env_grounding_threshold(recommended)
    reload_settings()
    print(f"recommended={recommended}")
    print(f"env={get_settings().grounding_threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
