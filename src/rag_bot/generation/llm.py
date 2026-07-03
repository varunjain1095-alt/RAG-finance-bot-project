"""Claude API client."""

import httpx

from rag_bot.config import get_settings

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MAX_TOKENS = 1024


class ClaudeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def generate_completion(
    prompt: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    extra_instruction: str | None = None,
) -> tuple[str, ClaudeUsage]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    user_content = prompt
    if extra_instruction:
        user_content = f"{extra_instruction}\n\n{prompt}"

    response = httpx.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.anthropic_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()

    text_blocks = [
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]
    text = "\n".join(text_blocks).strip()
    usage = data.get("usage", {})
    return text, ClaudeUsage(
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )
