"""Per-query API cost estimates (USD)."""

from rag_bot.generation.llm import ClaudeUsage

VOYAGE_EMBED_PER_1K = 0.00012
VOYAGE_RERANK_PER_1K = 0.00015
CLAUDE_INPUT_PER_1K = 0.003
CLAUDE_OUTPUT_PER_1K = 0.015


def estimate_cost_usd(
    *,
    embed_chars: int = 0,
    rerank_docs: int = 0,
    claude_usage: ClaudeUsage | None = None,
    rerank_used: bool = False,
) -> float:
    embed_tokens = max(embed_chars / 4, 0)
    cost = (embed_tokens / 1000) * VOYAGE_EMBED_PER_1K
    if rerank_used:
        cost += (rerank_docs * 200 / 1000) * VOYAGE_RERANK_PER_1K
    if claude_usage:
        cost += (claude_usage.input_tokens / 1000) * CLAUDE_INPUT_PER_1K
        cost += (claude_usage.output_tokens / 1000) * CLAUDE_OUTPUT_PER_1K
    return round(cost, 6)
