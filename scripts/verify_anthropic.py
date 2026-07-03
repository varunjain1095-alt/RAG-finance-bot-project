"""Verify ANTHROPIC_API_KEY and model id (no secrets printed)."""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

API_URL = "https://api.anthropic.com/v1/messages"


def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()

    if not key:
        print("ANTHROPIC_API_KEY: missing — set in .env")
        return 1
    if not key.startswith("sk-ant-"):
        print("ANTHROPIC_API_KEY: unexpected format (expected sk-ant-…)")
        return 1

    print(f"ANTHROPIC_API_KEY: present (len={len(key)})")
    print(f"ANTHROPIC_MODEL: {model}")

    response = httpx.post(
        API_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "Reply with OK only."}],
        },
        timeout=60.0,
    )

    print(f"HTTP status: {response.status_code}")

    if response.status_code == 200:
        print("API key and model: OK")
        return 0

    try:
        err = response.json().get("error", {})
        print(f"error_type: {err.get('type', 'unknown')}")
        msg = str(err.get("message", response.text))
        print(f"error_message: {msg[:200]}")
    except Exception:
        print("error_message: (non-JSON response)")

    if response.status_code in (401, 403):
        print("Hint: API key may be invalid or rotated — update ANTHROPIC_API_KEY in .env")
    elif response.status_code == 404:
        print("Hint: model id may be wrong for this account — check ANTHROPIC_MODEL")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
