"""Capture first-call raw output vs serial regen triggers."""

from __future__ import annotations

import re
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

from rag_bot.config import get_settings, reload_settings
from rag_bot.generation.citations import (
    enforce_citation,
    parse_citation_block,
    pick_citation_parent,
    strip_response_tags,
    top_parent_rerank_score,
)
from rag_bot.generation.llm import generate_completion
from rag_bot.generation.logging_db import create_session, load_session_state
from rag_bot.generation.pipeline import _parents_to_sources_text
from rag_bot.generation.prompts import assemble_prompt
from rag_bot.generation.serial_explanations import (
    answer_has_expected_closing,
    detect_scope_violations,
    filter_scope_violating_sentences,
    format_serial_prompt_block,
    get_catalog,
    get_expected_closing,
    is_serial_runaway_body,
)
from rag_bot.generation.session_state import build_conversation_context
from rag_bot.generation.serial_explanations import SerialExplanationState
from rag_bot.ingestion.embeddings import verify_embedding_model_startup
from rag_bot.retrieval.pipeline import retrieve


QUESTION = "what is a mutual fund"


def extract_serial_block(prompt: str) -> str:
    m = re.search(
        r"(## Serial explanation mode.*?)(?=\n## Retrieved sources|\Z)",
        prompt,
        re.S,
    )
    return m.group(1).strip() if m else ""


def main() -> int:
    reload_settings()
    settings = get_settings()
    verify_embedding_model_startup()

    # Warm
    warm = create_session(experience_level="new")
    from rag_bot.generation.pipeline import ask

    ask(warm, "what is expense ratio")

    session_id = create_session(experience_level="new")
    state = load_session_state(session_id)
    retrieval = retrieve(QUESTION)
    catalog = get_catalog("mutual_funds_intro")
    section = catalog.sections[0]
    serial = SerialExplanationState(
        topic_id="mutual_funds_intro",
        anchor_question=QUESTION,
        status="active",
        retrieved_parent_ids=[p.parent_chunk_id for p in retrieval.parents],
    )
    conversation_state = build_conversation_context(session_id, state, QUESTION)
    serial_block = format_serial_prompt_block(section, is_last=False, follow_up_labels=None)
    expected_closing = get_expected_closing(section, is_last=False, follow_up_labels=None)
    sources_text = _parents_to_sources_text(retrieval.parents)
    prompt = assemble_prompt(
        experience_level="new",
        retrieved_sources=sources_text,
        user_question=f"{QUESTION} (section: {section.display_title})",
        conversation_state=conversation_state,
        serial_section_block=serial_block,
    )

    print("=== Config ===")
    print(f"model: {settings.anthropic_model}")
    print(f"retrieved parents: {len(retrieval.parents)}")
    for i, p in enumerate(retrieval.parents, 1):
        print(
            f"  parent {i}: score={p.rerank_score:.3f} "
            f"chars={len(p.formatted_text)} source={p.source_name[:50]}"
        )
    print(f"prompt chars: {len(prompt)}")
    print(f"retrieved_sources chars: {len(sources_text)}")

    print("\n=== serial_section_block (in prompt) ===")
    print(extract_serial_block(prompt))

    print(f"\n=== expected_closing (exact match required) ===")
    print(repr(expected_closing))

    raw_output, usage = generate_completion(prompt)
    print("\n=== FIRST CALL raw_llm_output ===")
    print(raw_output)

    parsed = parse_citation_block(raw_output)
    body = strip_response_tags(parsed.body or raw_output)
    print("\n=== FIRST CALL body (stripped tags) ===")
    print(body)

    citation_parent = pick_citation_parent(retrieval.parents, serial.anchor_question)
    final_answer, citation_flow, _ = enforce_citation(
        raw_output,
        retrieval.parents,
        regen_output=None,
        user_question=serial.anchor_question,
        top_rerank_score=top_parent_rerank_score(retrieval.parents),
        grounding_threshold=settings.grounding_threshold,
    )
    parsed_final = parse_citation_block(final_answer)
    section_body = parsed_final.body or ""
    filtered_body = filter_scope_violating_sentences(
        catalog.topic_id, section.id, section_body
    )
    violations = detect_scope_violations(catalog.topic_id, section.id, section_body)
    violations_filtered = detect_scope_violations(
        catalog.topic_id, section.id, filtered_body
    )
    has_closing_raw = answer_has_expected_closing(final_answer, expected_closing)
    has_closing_filtered = (
        answer_has_expected_closing(
            rebuild := final_answer.replace(
                section_body, filtered_body, 1
            ) if filtered_body != section_body else final_answer,
            expected_closing,
        )
        if filtered_body != section_body
        else has_closing_raw
    )

    print("\n=== AFTER enforce_citation (no citation regen) ===")
    print(final_answer)
    print("\n=== citation_flow ===")
    print(citation_flow.to_dict())

    print("\n=== Regen trigger analysis ===")
    print(f"scope violations (raw body): {violations}")
    print(f"scope violations (after filter): {violations_filtered}")
    print(f"body changed by filter: {filtered_body != section_body}")
    if filtered_body != section_body:
        print("filtered_body:", filtered_body)
    print(f"answer_has_expected_closing (on final_answer): {has_closing_raw}")
    print(f"runaway body: {is_serial_runaway_body(filtered_body or section_body)}")
    print(
        f"needs_serial_regen would be: "
        f"{violations or (expected_closing and not has_closing_raw)}"
    )

  # Phrasing analysis
    body_for_check = parsed_final.body or ""
    if expected_closing:
        if expected_closing in body_for_check:
            print("closing match: EXACT substring found")
        else:
            print("closing match: EXACT substring NOT found")
            # similar variants
            variants = [
                expected_closing.replace(" me ", " "),
                expected_closing.replace("Would you like me to", "Would you like to"),
                "key mechanics",
            ]
            for v in variants:
                if v.lower() in body_for_check.lower():
                    print(f"  partial/variant found: {v!r}")

    print(f"\nfirst call tokens: in={usage.input_tokens} out={usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
