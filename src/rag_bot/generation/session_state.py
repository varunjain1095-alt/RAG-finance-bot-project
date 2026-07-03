"""Context reignition: structured session state and conversation context assembly."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import tiktoken

from rag_bot.generation.experience_level import ExperienceLevelCommand
from rag_bot.generation.serial_explanations import (
    SerialExplanationState,
    format_serial_facts_block,
)
from rag_bot.generation.turn_embeddings import (
    backfill_session_turn_embeddings,
    retrieve_relevant_turns,
    store_turn_embedding,
)
from rag_bot.retrieval.schemes import SchemeDetectionKind, detect_scheme

logger = logging.getLogger(__name__)

ROLLING_TURN_WINDOW = 5
STATE_TOKEN_THRESHOLD = 5000
_TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")


@dataclass
class SessionState:
    schemes_discussed: list[str] = field(default_factory=list)
    active_scheme: str | None = None
    refusal_events: list[dict[str, str]] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    recent_turns: list[dict[str, str]] = field(default_factory=list)
    retrieval_mode: bool = False
    turns_backfilled: bool = False
    turn_count: int = 0
    completed_serial_catalog_ids: list[str] = field(default_factory=list)
    serial_explanation: SerialExplanationState | None = None

    @classmethod
    def from_db(cls, raw: Any) -> SessionState:
        if not raw:
            return cls()
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = dict(raw)
        return cls(
            schemes_discussed=list(data.get("schemes_discussed") or []),
            active_scheme=data.get("active_scheme"),
            refusal_events=list(data.get("refusal_events") or []),
            preferences=list(data.get("preferences") or []),
            recent_turns=list(data.get("recent_turns") or []),
            retrieval_mode=bool(data.get("retrieval_mode")),
            turns_backfilled=bool(data.get("turns_backfilled")),
            turn_count=int(data.get("turn_count") or 0),
            completed_serial_catalog_ids=list(
                data.get("completed_serial_catalog_ids") or []
            ),
            serial_explanation=(
                SerialExplanationState.from_dict(data["serial_explanation"])
                if data.get("serial_explanation")
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemes_discussed": self.schemes_discussed,
            "active_scheme": self.active_scheme,
            "refusal_events": self.refusal_events,
            "preferences": self.preferences,
            "recent_turns": self.recent_turns,
            "retrieval_mode": self.retrieval_mode,
            "turns_backfilled": self.turns_backfilled,
            "turn_count": self.turn_count,
            "completed_serial_catalog_ids": self.completed_serial_catalog_ids,
            "serial_explanation": (
                self.serial_explanation.to_dict() if self.serial_explanation else None
            ),
        }


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_TOKEN_ENCODER.encode(text))


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _append_preference(state: SessionState, preference: str) -> None:
    if preference not in state.preferences:
        state.preferences.append(preference)


def apply_scheme_detection(state: SessionState, question: str) -> None:
    detection = detect_scheme(question)
    if detection.kind == SchemeDetectionKind.MATCHED and detection.scheme_name:
        _append_unique(state.schemes_discussed, detection.scheme_name)
        state.active_scheme = detection.scheme_name


def apply_level_command(state: SessionState, command: ExperienceLevelCommand) -> None:
    _append_preference(state, command.preference)


def apply_refusal_event(state: SessionState, category: str, question: str) -> None:
    state.refusal_events.append(
        {
            "category": category,
            "question": question[:200],
        }
    )


def append_recent_turn(
    state: SessionState,
    *,
    turn_id: uuid.UUID,
    question: str,
    answer: str,
) -> None:
    state.recent_turns.append(
        {
            "turn_id": str(turn_id),
            "question": question,
            "answer": answer,
        }
    )
    if len(state.recent_turns) > ROLLING_TURN_WINDOW:
        state.recent_turns = state.recent_turns[-ROLLING_TURN_WINDOW:]
    state.turn_count += 1


def format_structured_facts(state: SessionState) -> str:
    lines: list[str] = ["Structured session facts:"]
    if state.schemes_discussed:
        lines.append(
            "Schemes discussed: " + ", ".join(state.schemes_discussed)
        )
    if state.active_scheme:
        lines.append(f"Most recently discussed scheme: {state.active_scheme}")
    if state.refusal_events:
        summaries = [
            f"{event['category']} (\"{event['question'][:80]}…\")"
            if len(event["question"]) > 80
            else f"{event['category']} (\"{event['question']}\")"
            for event in state.refusal_events[-5:]
        ]
        lines.append("Prior refusals in this session: " + "; ".join(summaries))
    if state.preferences:
        lines.append("User preferences: " + ", ".join(state.preferences))
    if state.serial_explanation and state.serial_explanation.status == "active":
        lines.append(format_serial_facts_block(state.serial_explanation))
    if state.completed_serial_catalog_ids:
        lines.append(
            "Completed serial explainers: "
            + ", ".join(state.completed_serial_catalog_ids)
        )
    if len(lines) == 1:
        lines.append("No prior structured facts yet.")
    return "\n".join(lines)


def format_recent_turns(turns: list[dict[str, str]]) -> str:
    if not turns:
        return "Recent conversation: No prior turns in this session."
    lines = ["Recent conversation (last turns):"]
    for turn in turns:
        lines.append(f"User: {turn['question']}")
        lines.append(f"Bot: {turn['answer']}")
    return "\n".join(lines)


def _maybe_enable_retrieval_mode(state: SessionState, structured: str, turns_text: str) -> None:
    if state.retrieval_mode:
        return
    total = estimate_tokens(structured + "\n\n" + turns_text)
    if total >= STATE_TOKEN_THRESHOLD:
        state.retrieval_mode = True
        logger.info(
            "Session state crossed %d tokens — enabling retrieval mode",
            STATE_TOKEN_THRESHOLD,
        )


def build_conversation_context(
    session_id: uuid.UUID,
    state: SessionState,
    current_question: str,
) -> str:
    structured = format_structured_facts(state)
    recent_text = format_recent_turns(state.recent_turns)

    if not state.retrieval_mode:
        _maybe_enable_retrieval_mode(state, structured, recent_text)
        if state.retrieval_mode:
            backfill_session_turn_embeddings(session_id)
            state.turns_backfilled = True

    if state.retrieval_mode:
        if not state.turns_backfilled:
            backfill_session_turn_embeddings(session_id)
            state.turns_backfilled = True
        relevant = retrieve_relevant_turns(session_id, current_question)
        if relevant:
            retrieved_block = "Relevant prior exchanges:\n" + "\n".join(relevant)
        else:
            retrieved_block = "Relevant prior exchanges: None indexed yet."
        return f"{structured}\n\n{retrieved_block}"

    return f"{structured}\n\n{recent_text}"


def finalize_turn_in_state(
    session_id: uuid.UUID,
    state: SessionState,
    *,
    turn_id: uuid.UUID,
    question: str,
    answer: str,
    refusal_category: str | None,
    level_command: ExperienceLevelCommand | None,
) -> SessionState:
    apply_scheme_detection(state, question)
    if level_command:
        apply_level_command(state, level_command)
    if refusal_category:
        apply_refusal_event(state, refusal_category, question)
    append_recent_turn(state, turn_id=turn_id, question=question, answer=answer)

    if state.retrieval_mode or state.turn_count >= ROLLING_TURN_WINDOW:
        store_turn_embedding(session_id, turn_id, state.turn_count, question, answer)

    return state
