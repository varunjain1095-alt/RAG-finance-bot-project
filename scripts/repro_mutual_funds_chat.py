"""E2E /chat test: what is a mutual fund → New → serial section 1 + offer_next."""

import json
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

import httpx

from rag_bot.config import reload_settings
from rag_bot.generation.logging_db import create_session


def main() -> int:
    reload_settings()
    base = "http://localhost:8000"
    question = "what is a mutual fund"

    with httpx.Client(timeout=120.0) as client:
        session_id = create_session(experience_level="somewhat_familiar")
        print("session_id:", session_id)

        r = client.post(
            f"{base}/session/{session_id}/experience-level",
            json={"experience_level": "new"},
        )
        print("experience-level:", r.status_code)

        # Warm + timed run
        for label in ("warm", "timed"):
            start = time.perf_counter()
            r = client.post(
                f"{base}/chat",
                json={"session_id": str(session_id), "message": question},
            )
            elapsed = time.perf_counter() - start
            print(f"/chat {label}: status={r.status_code} elapsed={elapsed:.3f}s")

            if r.status_code != 200:
                print(r.text[:500])
                return 1

            data = r.json()
            answer = data.get("answer", "")
            print("answer preview:", answer[:280].replace("\n", " "))
            print("timings_ms:", json.dumps(data.get("timings_ms", {})))

            lower = answer.lower()
            has_offer = "would you like" in lower or "key mechanics" in lower
            print("offer_next present:", has_offer)

            if label == "timed" and not has_offer:
                print("ERROR: missing offer_next closing question")
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
