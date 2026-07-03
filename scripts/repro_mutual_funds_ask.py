"""Reproduce explain mutual funds via ask() directly — capture traceback."""

import traceback
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

from rag_bot.config import reload_settings
from rag_bot.generation.logging_db import create_session
from rag_bot.generation.pipeline import ask
from rag_bot.operations.chat_errors import categorize_chat_exception, log_chat_failure


def main() -> int:
    reload_settings()
    session_id = create_session(experience_level="new")
    question = "explain mutual funds"
    print("session_id:", session_id)

    try:
        result = ask(session_id, question)
        print("SUCCESS")
        print("answer preview:", result.answer[:300])
        return 0
    except Exception as exc:
        category = categorize_chat_exception(exc)
        log_chat_failure(
            exc=exc,
            category=category,
            session_id=session_id,
            message=question,
        )
        print("CATEGORY:", category.value)
        print("EXCEPTION:", type(exc).__name__, exc)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
