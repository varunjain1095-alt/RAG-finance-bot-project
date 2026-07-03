"""Run N first-call simulations and count regen triggers."""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

from rag_bot.config import reload_settings
from rag_bot.generation.citations import enforce_citation, parse_citation_block, pick_citation_parent, strip_response_tags, top_parent_rerank_score
from rag_bot.generation.llm import generate_completion
from rag_bot.generation.logging_db import create_session
from rag_bot.generation.pipeline import _parents_to_sources_text, ask
from rag_bot.generation.prompts import assemble_prompt
from rag_bot.generation.serial_explanations import (
    answer_has_expected_closing,
    detect_scope_violations,
    filter_scope_violating_sentences,
    format_serial_prompt_block,
    get_catalog,
    get_expected_closing,
)
from rag_bot.generation.session_state import build_conversation_context
from rag_bot.generation.serial_explanations import SerialExplanationState
from rag_bot.ingestion.embeddings import verify_embedding_model_startup
from rag_bot.retrieval.pipeline import retrieve

QUESTION = "what is a mutual fund"
N = 3


def pipeline_would_regen(raw_output, parents, catalog, section, expected_closing, serial) -> dict:
    from rag_bot.config import get_settings
    settings = get_settings()
    final_answer, _, _ = enforce_citation(
        raw_output,
        parents,
        user_question=serial.anchor_question,
        top_rerank_score=top_parent_rerank_score(parents),
        grounding_threshold=settings.grounding_threshold,
    )
    parsed_final = parse_citation_block(final_answer)
    section_body = parsed_final.body or ""
    filtered = filter_scope_violating_sentences(catalog.topic_id, section.id, section_body)
    if filtered != section_body:
        from rag_bot.generation.serial_explanations import rebuild_answer_with_body
        final_answer = rebuild_answer_with_body(final_answer, filtered)
    violations = detect_scope_violations(catalog.topic_id, section.id, filtered)
    has_closing = answer_has_expected_closing(final_answer, expected_closing)
    return {
        "violations_after_filter": violations,
        "has_closing": has_closing,
        "would_regen": bool(violations or (expected_closing and not has_closing)),
        "raw_violations": detect_scope_violations(catalog.topic_id, section.id, section_body),
        "has_closing_raw": answer_has_expected_closing(final_answer, expected_closing) if filtered == section_body else answer_has_expected_closing(
            __import__("rag_bot.generation.serial_explanations", fromlist=["rebuild_answer_with_body"]).rebuild_answer_with_body(final_answer, filtered),
            expected_closing,
        ),
    }


def main() -> int:
    reload_settings()
    verify_embedding_model_startup()
    warm = create_session(experience_level="new")
    ask(warm, "what is expense ratio")

    retrieval = retrieve(QUESTION)
    catalog = get_catalog("mutual_funds_intro")
    section = catalog.sections[0]
    serial = SerialExplanationState(
        topic_id="mutual_funds_intro",
        anchor_question=QUESTION,
        status="active",
        retrieved_parent_ids=[p.parent_chunk_id for p in retrieval.parents],
    )
    session_id = create_session(experience_level="new")
    from rag_bot.generation.logging_db import load_session_state
    state = load_session_state(session_id)
    conversation_state = build_conversation_context(session_id, state, QUESTION)
    serial_block = format_serial_prompt_block(section, is_last=False, follow_up_labels=None)
    expected = get_expected_closing(section, is_last=False, follow_up_labels=None)
    prompt = assemble_prompt(
        experience_level="new",
        retrieved_sources=_parents_to_sources_text(retrieval.parents),
        user_question=f"{QUESTION} (section: {section.display_title})",
        conversation_state=conversation_state,
        serial_section_block=serial_block,
    )

    for i in range(N):
        raw, _ = generate_completion(prompt)
        r = pipeline_would_regen(raw, retrieval.parents, catalog, section, expected, serial)
        print(f"run {i+1}: would_regen={r['would_regen']} raw_violations={r['raw_violations']} "
              f"after_filter={r['violations_after_filter']} has_closing={r['has_closing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
