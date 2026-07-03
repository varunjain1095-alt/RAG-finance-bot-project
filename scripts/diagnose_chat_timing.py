"""Detailed timing breakdown for one warm /chat turn."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

from rag_bot.config import get_settings, reload_settings
from rag_bot.generation.llm import generate_completion as _generate_completion
from rag_bot.generation.logging_db import create_session, get_connection
from rag_bot.generation.pipeline import ask
from rag_bot.ingestion.embeddings import verify_embedding_model_startup

QUESTION = "what is a mutual fund"


@dataclass
class LlmCallRecord:
    index: int
    reason: str
    elapsed_ms: float
    input_tokens: int
    output_tokens: int
    extra_instruction_chars: int
    user_content_chars: int


@dataclass
class LlmInstrumentation:
    calls: list[LlmCallRecord] = field(default_factory=list)
    _reason_stack: list[str] = field(default_factory=list)

    def push_reason(self, reason: str) -> None:
        self._reason_stack.append(reason)

    def pop_reason(self) -> None:
        if self._reason_stack:
            self._reason_stack.pop()

    def record(
        self,
        elapsed_ms: float,
        usage,
        prompt: str,
        extra_instruction: str | None,
        reason: str,
    ) -> None:
        extra = extra_instruction or ""
        user_content = f"{extra}\n\n{prompt}" if extra else prompt
        self.calls.append(
            LlmCallRecord(
                index=len(self.calls) + 1,
                reason=reason,
                elapsed_ms=elapsed_ms,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                extra_instruction_chars=len(extra),
                user_content_chars=len(user_content),
            )
        )


instrumentation = LlmInstrumentation()


def classify_llm_call(extra_instruction: str | None) -> str:
    if not extra_instruction:
        return "initial_generation"
    lower = extra_instruction.lower()
    if "prior answer lacked a valid citation" in lower:
        return "citation_regen"
    if "runaway" in lower or "too long" in lower or "one section" in lower:
        return "serial_runaway_regen"
    if "closing" in lower or "scope" in lower or "section" in lower:
        return "serial_scope_or_closing_regen"
    return "regen_other"


def instrumented_generate_completion(
    prompt: str,
    *,
    max_tokens: int = 1024,
    extra_instruction: str | None = None,
):
    reason = classify_llm_call(extra_instruction)
    start = time.perf_counter()
    text, usage = _generate_completion(
        prompt,
        max_tokens=max_tokens,
        extra_instruction=extra_instruction,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    instrumentation.record(elapsed_ms, usage, prompt, extra_instruction, reason)
    return text, usage


def estimate_tokens(text: str) -> int:
    # Rough English heuristic (~4 chars/token); API usage is authoritative for LLM calls.
    return max(1, len(text) // 4)


def fetch_query_log(turn_id: uuid.UUID) -> dict[str, Any]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT turn_id, user_question, experience_level,
                   final_prompt, citation_flow, refusal_category,
                   latency_input_filters_ms, latency_embedding_ms,
                   latency_retrieval_ms, latency_rerank_ms,
                   latency_generation_ms, latency_postprocessing_ms,
                   latency_total_ms, cost_usd,
                   LENGTH(final_prompt) AS final_prompt_chars,
                   jsonb_array_length(retrieved_chunks) AS retrieved_parent_count
            FROM query_logs
            WHERE turn_id = %s
            """,
            (turn_id,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"No query_log for turn_id={turn_id}")
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def section_breakdown(final_prompt: str) -> dict[str, int]:
    markers = [
        ("static_system (before experience)", "## Identity"),
        ("experience_level", "{{experience_level_instructions}}"),
        ("few_shot_examples", "### Example:"),
        ("conversation_state", "## Conversation state"),
        ("serial_section_block", "## Serial explanation mode"),
        ("retrieved_sources", "## Retrieved sources"),
        ("user_question", "## User question"),
    ]
    sizes: dict[str, int] = {}
    for label, marker in markers:
        start = final_prompt.find(marker)
        if start < 0:
            continue
        if label == "few_shot_examples":
            # First few-shot through start of retrieved sources or conversation
            end = len(final_prompt)
            for end_marker in ("## Conversation state", "## Serial explanation mode", "## Retrieved sources"):
                pos = final_prompt.find(end_marker, start)
                if pos >= 0:
                    end = min(end, pos)
            sizes[label] = end - start
            continue
        if label == "static_system (before experience)":
            end = final_prompt.find("{{experience_level_instructions}}")
            if end < 0:
                end = final_prompt.find("## Retrieved sources")
            sizes[label] = end - start if end > start else len(final_prompt) - start
            continue
        # default: until next known header
        end = len(final_prompt)
        for _, later in markers:
            if later == marker:
                continue
            pos = final_prompt.find(later, start + len(marker))
            if pos >= 0:
                end = min(end, pos)
        sizes[label] = end - start
    return sizes


def main() -> int:
    reload_settings()
    settings = get_settings()

    print("=== Runtime configuration ===")
    print(f"ANTHROPIC_MODEL (get_settings): {settings.anthropic_model}")
    print(f"ANTHROPIC_MODEL (os.environ):     {__import__('os').environ.get('ANTHROPIC_MODEL', '<unset>')}")
    print(f"GROUNDING_THRESHOLD:              {settings.grounding_threshold}")

    verify_embedding_model_startup()
    print("\n=== Warm-up ===")
    warm_session = create_session(experience_level="new")
    ask(warm_session, "what is expense ratio")
    print(f"warm-up turn complete (session {warm_session})")

    # Instrument pipeline LLM calls for the measured turn only.
    import rag_bot.generation.pipeline as pipeline_mod

    original = pipeline_mod.generate_completion
    pipeline_mod.generate_completion = instrumented_generate_completion

    print("\n=== Measured turn ===")
    session_id = create_session(experience_level="new")
    wall_start = time.perf_counter()
    try:
        result = ask(session_id, QUESTION)
    finally:
        pipeline_mod.generate_completion = original
    wall_elapsed = time.perf_counter() - wall_start

    log = fetch_query_log(result.turn_id)
    final_prompt = log.get("final_prompt") or ""
    citation_flow = log.get("citation_flow") or {}

    print(f"session_id: {session_id}")
    print(f"turn_id:    {result.turn_id}")
    print(f"wall_clock_s: {wall_elapsed:.3f}")

    print("\n=== Prompt size (final_prompt from query_logs) ===")
    print(f"characters: {len(final_prompt)}")
    print(f"est_tokens (~chars/4): {estimate_tokens(final_prompt)}")
    print(f"retrieved parent count: {log.get('retrieved_parent_count')}")
    for section, chars in section_breakdown(final_prompt).items():
        print(f"  {section}: {chars} chars (~{chars // 4} tok est)")

    print("\n=== LLM calls this turn ===")
    print(f"total_api_calls: {len(instrumentation.calls)}")
    total_in = 0
    total_out = 0
    for call in instrumentation.calls:
        total_in += call.input_tokens
        total_out += call.output_tokens
        print(
            f"  #{call.index} {call.reason}: "
            f"{call.elapsed_ms:.0f}ms "
            f"in={call.input_tokens} out={call.output_tokens} tok "
            f"user_content_chars={call.user_content_chars}"
        )
    print(f"aggregate_api_usage: in={total_in} out={total_out} tokens")

    print("\n=== citation_flow (regeneration signals) ===")
    print(json.dumps(citation_flow, indent=2))

    print("\n=== query_logs latency breakdown (ms) ===")
    stages = [
        ("input_filters", log["latency_input_filters_ms"]),
        ("embedding", log["latency_embedding_ms"]),
        ("retrieval", log["latency_retrieval_ms"]),
        ("rerank", log["latency_rerank_ms"]),
        ("generation", log["latency_generation_ms"]),
        ("postprocessing", log["latency_postprocessing_ms"]),
        ("total", log["latency_total_ms"]),
    ]
    for name, ms in stages:
        print(f"  latency_{name}_ms: {ms}")

    non_gen = (
        log["latency_input_filters_ms"]
        + log["latency_embedding_ms"]
        + log["latency_retrieval_ms"]
        + log["latency_rerank_ms"]
        + log["latency_postprocessing_ms"]
    )
    print(f"  non_generation_subtotal_ms: {non_gen}")
    print(f"  generation_isolated_ms (query_logs): {log['latency_generation_ms']}")

    print("\n=== Pipeline timings object (AskResult) ===")
    print(
        json.dumps(
            {
                "input_filters": round(result.timings.input_filters_ms, 1),
                "embedding": round(result.timings.embedding_ms, 1),
                "retrieval": round(result.timings.retrieval_ms, 1),
                "rerank": round(result.timings.rerank_ms, 1),
                "generation": round(result.timings.generation_ms, 1),
                "postprocessing": round(result.timings.postprocessing_ms, 1),
                "total": round(result.timings.total_ms, 1),
            },
            indent=2,
        )
    )

    print("\n=== debug flags ===")
    print(json.dumps(result.debug, indent=2))
    print(f"cost_usd: {log['cost_usd']}")
    offer = "Would you like me to run through the key mechanics?"
    print(f"offer_next present: {offer.lower() in result.answer.lower()}")
    print(f"cited_url: {result.cited_url}")
    print(f"citation_flow: {json.dumps(result.citation_flow.to_dict())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
