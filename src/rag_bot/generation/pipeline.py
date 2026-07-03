"""Full query pipeline: filters → retrieval → generation → citation → logging."""

import logging
import time
import uuid

from rag_bot.generation.citations import (
    enforce_citation,
    is_runaway_body,
    parse_citation_block,
    pick_citation_parent,
    strip_response_tags,
    top_parent_rerank_score,
)
from rag_bot.generation.clarification import (
    format_clarification_prompt_block,
    format_non_serial_clarification_block,
    get_catalog_for_serial,
    is_clarification_request,
    resolve_serial_section_for_clarification,
)
from rag_bot.config import get_settings
from rag_bot.generation.cost import estimate_cost_usd
from rag_bot.generation.experience_level import (
    detect_experience_level_command,
    level_acknowledgment,
)
from rag_bot.generation.filters import (
    FilterResultKind,
    is_investment_recommendation_request,
    run_input_filters,
)
from rag_bot.generation.llm import ClaudeUsage, generate_completion
from rag_bot.generation.logging_db import (
    get_session_experience_level,
    load_session_state,
    log_pii_refusal,
    log_query_turn,
    save_session_state,
    update_session_experience_level,
)
from rag_bot.generation.prompts import assemble_prompt
from rag_bot.generation.refusals import (
    clarification_followup_message,
    investment_recommendation_refusal_message,
    no_performance_refusal_message,
    out_of_scope_refusal_message,
    pii_refusal_message,
    runaway_fallback_message,
)
from rag_bot.generation.serial_explanations import (
    SerialExplanationState,
    build_serial_regen_instruction,
    detect_scope_violations,
    detect_serial_topic,
    ensure_serial_closing,
    filter_scope_violating_sentences,
    format_serial_prompt_block,
    get_catalog,
    get_expected_closing,
    is_continuation_message,
    is_decline_message,
    is_serial_runaway_body,
    pick_follow_up_labels,
    rebuild_answer_with_body,
    resolve_section_for_continuation,
    truncate_serial_body,
)
from rag_bot.generation.session_state import (
    build_conversation_context,
    finalize_turn_in_state,
)
from rag_bot.retrieval.parents import load_parents_by_ids
from rag_bot.generation.types import (
    AskResult,
    CitationFlow,
    GenerationTimings,
    RefusalCategory,
)
from rag_bot.ingestion.db import apply_migrations
from rag_bot.retrieval.pipeline import retrieve
from rag_bot.retrieval.types import RetrievalOutcome

logger = logging.getLogger(__name__)

PII_REDACTED_PLACEHOLDER = "[redacted — PII detected]"

SERIAL_PROMPT_MAX_PARENTS = 2
SERIAL_PROMPT_PARENT_CHAR_CAP = 3000


def _parents_to_sources_text(parents) -> str:
    return "\n\n---\n\n".join(p.formatted_text for p in parents)


def _select_parents_for_serial_prompt(parents: list) -> list:
    """Top-ranked parents for serial generation prompt; citation pool stays full."""
    if not parents:
        return []
    ranked = sorted(parents, key=lambda p: -(p.rerank_score or 0))
    selected = [ranked[0]]
    if len(ranked) > 1:
        first_len = len(ranked[0].formatted_text or "")
        second_len = len(ranked[1].formatted_text or "")
        if first_len + second_len <= SERIAL_PROMPT_PARENT_CHAR_CAP:
            selected.append(ranked[1])
    return selected


def _apply_serial_section_body_enforcement(
    final_answer: str,
    *,
    catalog_id: str,
    section_id: str,
    expected_closing: str | None,
) -> str:
    """Filter scope drift, cap runaway length, and append offer_next programmatically."""
    parsed_final = parse_citation_block(final_answer)
    section_body = parsed_final.body or ""
    section_body = filter_scope_violating_sentences(catalog_id, section_id, section_body)
    if is_serial_runaway_body(section_body):
        section_body = truncate_serial_body(section_body)
    if section_body != (parsed_final.body or ""):
        final_answer = rebuild_answer_with_body(final_answer, section_body)
    return ensure_serial_closing(final_answer, expected_closing)


def _parents_to_retrieved_chunks(parents) -> list[dict]:
    return [
        {
            "parent_chunk_id": p.parent_chunk_id,
            "source_name": p.source_name,
            "source_url": p.source_url,
            "date_version": p.date_version,
            "rerank_score": p.rerank_score,
            "text_snippet": p.text[:300],
        }
        for p in parents
    ]


def _record_turn(
    *,
    session_id: uuid.UUID,
    state,
    experience_level: str,
    user_question: str,
    answer: str,
    refusal_category: str | None,
    timings: GenerationTimings,
    retrieved_chunks: list[dict] | None = None,
    final_prompt: str | None = None,
    raw_llm_output: str | None = None,
    citation_flow: CitationFlow | None = None,
    cost_usd: float = 0.0,
    level_command=None,
) -> tuple[uuid.UUID, object]:
    flow = citation_flow or CitationFlow()
    turn_id = log_query_turn(
        session_id=session_id,
        experience_level=experience_level,
        user_question=user_question,
        final_answer=answer,
        retrieved_chunks=retrieved_chunks or [],
        final_prompt=final_prompt,
        raw_llm_output=raw_llm_output,
        cited_chunk_id=None,
        citation_flow=flow,
        refusal_category=refusal_category,
        timings=timings,
        cost_usd=cost_usd,
    )
    state = finalize_turn_in_state(
        session_id,
        state,
        turn_id=turn_id,
        question=user_question,
        answer=answer,
        refusal_category=refusal_category,
        level_command=level_command,
    )
    save_session_state(session_id, state)
    return turn_id, state


def _resolve_top_rerank_score(parents: list, retrieval=None) -> float | None:
    if retrieval is not None and retrieval.top_rerank_score is not None:
        return retrieval.top_rerank_score
    return top_parent_rerank_score(parents)


def _deliver_serial_section(
    *,
    session_id: uuid.UUID,
    state,
    experience_level: str,
    log_question: str,
    prompt_question: str,
    parents: list,
    catalog,
    section,
    conversation_state: str,
    timings: GenerationTimings,
    start_total: float,
    mixed_query: bool,
    rerank_used: bool,
    serial: SerialExplanationState,
    reexplain: bool = False,
) -> AskResult:
    is_last = section.id == catalog.sections[-1].id
    follow_up_labels = None
    if is_last:
        follow_up_labels = pick_follow_up_labels(
            catalog, state.completed_serial_catalog_ids
        )
    expected_closing = get_expected_closing(
        section, is_last=is_last, follow_up_labels=follow_up_labels
    )
    if reexplain:
        serial_block = format_clarification_prompt_block(
            section,
            user_message=log_question,
            expected_closing=expected_closing,
        )
    else:
        serial_block = format_serial_prompt_block(
            section,
            catalog_id=catalog.topic_id,
            is_last=is_last,
            follow_up_labels=follow_up_labels,
        )
    prompt_parents = _select_parents_for_serial_prompt(parents)
    sources_text = _parents_to_sources_text(prompt_parents)
    prompt = assemble_prompt(
        experience_level=experience_level,
        retrieved_sources=sources_text,
        user_question=prompt_question,
        conversation_state=conversation_state,
        serial_section_block=serial_block,
    )

    t0 = time.perf_counter()
    raw_output, usage = generate_completion(prompt)
    timings.generation_ms = (time.perf_counter() - t0) * 1000

    parsed = parse_citation_block(raw_output)
    body = strip_response_tags(parsed.body or raw_output)
    if is_serial_runaway_body(body):
        t0 = time.perf_counter()
        runaway_regen, runaway_usage = generate_completion(
            prompt,
            extra_instruction=build_serial_regen_instruction(
                section, catalog, [], expected_closing
            ),
        )
        timings.generation_ms += (time.perf_counter() - t0) * 1000
        usage = ClaudeUsage(
            input_tokens=usage.input_tokens + runaway_usage.input_tokens,
            output_tokens=usage.output_tokens + runaway_usage.output_tokens,
        )
        raw_output = runaway_regen
        parsed = parse_citation_block(raw_output)
        body = strip_response_tags(parsed.body or raw_output)

    if is_serial_runaway_body(body):
        body = truncate_serial_body(body)
        raw_output = f"[FACTUAL] {body}"

    citation_parent = pick_citation_parent(parents, serial.anchor_question)
    refusal_category: str | None = (
        RefusalCategory.MIXED_FACTUAL_ADVISORY.value if mixed_query else None
    )

    regen_output: str | None = None
    first_parsed = parse_citation_block(raw_output)
    allowed_urls = {p.source_url for p in parents}
    needs_citation_regen = (
        not first_parsed.citation_url
        or first_parsed.citation_url not in allowed_urls
    )
    if needs_citation_regen:
        t0 = time.perf_counter()
        regen_output, regen_usage = generate_completion(
            prompt,
            extra_instruction=(
                "Your prior answer lacked a valid citation. "
                "Reply again with [FACTUAL] tag, answer body, "
                "Last updated from sources line, and Source line using "
                "ONLY URLs copied exactly from the retrieved sources above."
            ),
        )
        timings.generation_ms += (time.perf_counter() - t0) * 1000
        usage = ClaudeUsage(
            input_tokens=usage.input_tokens + regen_usage.input_tokens,
            output_tokens=usage.output_tokens + regen_usage.output_tokens,
        )

    t0 = time.perf_counter()
    final_answer, citation_flow, regen_applied = enforce_citation(
        raw_output,
        parents,
        regen_output=regen_output,
        user_question=serial.anchor_question,
        top_rerank_score=_resolve_top_rerank_score(parents),
        grounding_threshold=get_settings().grounding_threshold,
        clarification_context=reexplain,
    )
    timings.postprocessing_ms = (time.perf_counter() - t0) * 1000
    raw_llm_output = regen_applied or raw_output

    final_answer = _apply_serial_section_body_enforcement(
        final_answer,
        catalog_id=catalog.topic_id,
        section_id=section.id,
        expected_closing=expected_closing,
    )
    parsed_enforced = parse_citation_block(final_answer)
    section_body = parsed_enforced.body or ""
    violations = detect_scope_violations(
        catalog.topic_id, section.id, section_body
    )
    if violations:
        t0 = time.perf_counter()
        serial_regen, serial_regen_usage = generate_completion(
            prompt,
            extra_instruction=build_serial_regen_instruction(
                section,
                catalog,
                violations,
                expected_closing,
            ),
        )
        timings.generation_ms += (time.perf_counter() - t0) * 1000
        usage = ClaudeUsage(
            input_tokens=usage.input_tokens + serial_regen_usage.input_tokens,
            output_tokens=usage.output_tokens + serial_regen_usage.output_tokens,
        )
        final_answer, citation_flow, regen_applied = enforce_citation(
            serial_regen,
            parents,
            user_question=serial.anchor_question,
            top_rerank_score=_resolve_top_rerank_score(parents),
            grounding_threshold=get_settings().grounding_threshold,
            clarification_context=reexplain,
        )
        raw_llm_output = regen_applied or serial_regen
        final_answer = _apply_serial_section_body_enforcement(
            final_answer,
            catalog_id=catalog.topic_id,
            section_id=section.id,
            expected_closing=expected_closing,
        )

    cost_usd = estimate_cost_usd(
        embed_chars=len(prompt_question),
        rerank_docs=len(parents),
        claude_usage=usage,
        rerank_used=rerank_used,
    )

    if section.id not in serial.delivered_section_ids:
        serial.delivered_section_ids.append(section.id)
    if is_last:
        serial.status = "completed"
        if catalog.topic_id not in state.completed_serial_catalog_ids:
            state.completed_serial_catalog_ids.append(catalog.topic_id)
        state.serial_explanation = None
    else:
        state.serial_explanation = serial

    timings.total_ms = (time.perf_counter() - start_total) * 1000
    save_session_state(session_id, state)

    turn_id, _ = _record_turn(
        session_id=session_id,
        state=state,
        experience_level=experience_level,
        user_question=log_question,
        answer=final_answer,
        refusal_category=refusal_category,
        timings=timings,
        retrieved_chunks=_parents_to_retrieved_chunks(parents),
        final_prompt=prompt,
        raw_llm_output=raw_llm_output,
        citation_flow=citation_flow,
        cost_usd=cost_usd,
    )

    return AskResult(
        turn_id=turn_id,
        session_id=session_id,
        answer=final_answer,
        refusal_category=refusal_category,
        cited_url=citation_flow.cited_url,
        experience_level=experience_level,
        timings=timings,
        cost_usd=cost_usd,
        citation_flow=citation_flow,
        debug={
            "serial_section": section.id,
            "mixed_query": mixed_query,
            "reexplain": reexplain,
        },
    )


def _handle_clarification_request(
    *,
    session_id: uuid.UUID,
    state,
    experience_level: str,
    question: str,
    mixed_query: bool,
    timings: GenerationTimings,
    start_total: float,
    serial: SerialExplanationState | None,
) -> AskResult | None:
    """Re-explain prior content; no fresh retrieval on the confusion phrase itself."""
    if serial and serial.status == "active":
        catalog = get_catalog_for_serial(serial)
        if catalog:
            section = resolve_serial_section_for_clarification(serial, catalog)
            parents = load_parents_by_ids(serial.retrieved_parent_ids)
            if parents:
                conversation_state = build_conversation_context(
                    session_id, state, serial.anchor_question
                )
                prompt_q = (
                    f"{serial.anchor_question} "
                    f"(clarification — re-explain: {section.display_title})"
                )
                return _deliver_serial_section(
                    session_id=session_id,
                    state=state,
                    experience_level=experience_level,
                    log_question=question,
                    prompt_question=prompt_q,
                    parents=parents,
                    catalog=catalog,
                    section=section,
                    conversation_state=conversation_state,
                    timings=timings,
                    start_total=start_total,
                    mixed_query=mixed_query,
                    rerank_used=True,
                    serial=serial,
                    reexplain=True,
                )

    if not state.recent_turns:
        return None

    last_turn = state.recent_turns[-1]
    prior_question = last_turn.get("question", "")
    prior_answer = last_turn.get("answer", "")
    if not prior_question:
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        answer = clarification_followup_message()
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=answer,
            refusal_category=None,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=answer,
            experience_level=experience_level,
            timings=timings,
        )

    retrieval = retrieve(prior_question)
    timings.embedding_ms = retrieval.timing.embed
    timings.retrieval_ms = retrieval.timing.retrieval
    timings.rerank_ms = retrieval.timing.rerank

    if retrieval.outcome != RetrievalOutcome.SUCCESS or not retrieval.parents:
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        answer = clarification_followup_message()
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=answer,
            refusal_category=None,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=answer,
            experience_level=experience_level,
            timings=timings,
        )

    parents = retrieval.parents
    clarification_block = format_non_serial_clarification_block(
        prior_question, prior_answer
    )
    sources_text = _parents_to_sources_text(parents)
    conversation_state = build_conversation_context(session_id, state, question)
    prompt = assemble_prompt(
        experience_level=experience_level,
        retrieved_sources=sources_text,
        user_question=question,
        conversation_state=conversation_state,
        serial_section_block=clarification_block,
    )

    t0 = time.perf_counter()
    raw_output, usage = generate_completion(prompt)
    timings.generation_ms = (time.perf_counter() - t0) * 1000

    parsed = parse_citation_block(raw_output)
    body = strip_response_tags(parsed.body or raw_output)
    citation_parent = pick_citation_parent(parents, prior_question)
    refusal_category: str | None = (
        RefusalCategory.MIXED_FACTUAL_ADVISORY.value if mixed_query else None
    )
    top_score = _resolve_top_rerank_score(parents, retrieval)

    if is_runaway_body(body, experience_level=experience_level, question=prior_question):
        final_answer = runaway_fallback_message(
            citation_parent.source_url, citation_parent.date_version
        )
        citation_flow = CitationFlow(
            final_outcome="runaway_fallback",
            cited_url=citation_parent.source_url,
            citation_present=True,
            url_provenance_passed=True,
        )
        raw_llm_output = raw_output
        cost_usd = estimate_cost_usd(
            embed_chars=len(question),
            rerank_docs=len(parents),
            rerank_used=retrieval.rerank_used,
        )
    else:
        regen_output: str | None = None
        first_parsed = parse_citation_block(raw_output)
        allowed_urls = {p.source_url for p in parents}
        if (
            not first_parsed.citation_url
            or first_parsed.citation_url not in allowed_urls
        ):
            t0 = time.perf_counter()
            regen_output, regen_usage = generate_completion(
                prompt,
                extra_instruction=(
                    "Your prior answer lacked a valid citation. "
                    "Reply again with [FACTUAL] tag, answer body, "
                    "Last updated from sources line, and Source line using "
                    "ONLY URLs copied exactly from the retrieved sources above."
                ),
            )
            timings.generation_ms += (time.perf_counter() - t0) * 1000
            usage = ClaudeUsage(
                input_tokens=usage.input_tokens + regen_usage.input_tokens,
                output_tokens=usage.output_tokens + regen_usage.output_tokens,
            )

        t0 = time.perf_counter()
        final_answer, citation_flow, regen_applied = enforce_citation(
            raw_output,
            parents,
            regen_output=regen_output,
            user_question=prior_question,
            top_rerank_score=top_score,
            grounding_threshold=get_settings().grounding_threshold,
            clarification_context=True,
        )
        timings.postprocessing_ms = (time.perf_counter() - t0) * 1000
        raw_llm_output = regen_applied or raw_output
        cost_usd = estimate_cost_usd(
            embed_chars=len(question),
            rerank_docs=len(parents),
            claude_usage=usage,
            rerank_used=retrieval.rerank_used,
        )

    timings.total_ms = (time.perf_counter() - start_total) * 1000
    turn_id, _ = _record_turn(
        session_id=session_id,
        state=state,
        experience_level=experience_level,
        user_question=question,
        answer=final_answer,
        refusal_category=refusal_category,
        timings=timings,
        retrieved_chunks=_parents_to_retrieved_chunks(parents),
        final_prompt=prompt,
        raw_llm_output=raw_llm_output,
        citation_flow=citation_flow,
        cost_usd=cost_usd,
    )
    return AskResult(
        turn_id=turn_id,
        session_id=session_id,
        answer=final_answer,
        refusal_category=refusal_category,
        cited_url=citation_flow.cited_url,
        experience_level=experience_level,
        timings=timings,
        cost_usd=cost_usd,
        citation_flow=citation_flow,
        debug={"clarification_reexplain": True, "anchor_question": prior_question},
    )


def ask(session_id: uuid.UUID, question: str) -> AskResult:
    """End-to-end query handling with Phase 4 session context."""
    apply_migrations()
    start_total = time.perf_counter()
    timings = GenerationTimings()
    experience_level = get_session_experience_level(session_id)
    state = load_session_state(session_id)

    level_command = detect_experience_level_command(question)
    if level_command:
        experience_level = update_session_experience_level(
            session_id, level_command.target_level
        )
        answer = level_acknowledgment(experience_level)
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=answer,
            refusal_category=None,
            timings=timings,
            level_command=level_command,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=answer,
            experience_level=experience_level,
            timings=timings,
        )

    t0 = time.perf_counter()
    filter_result = run_input_filters(question)
    timings.input_filters_ms = (time.perf_counter() - t0) * 1000

    if filter_result.kind == FilterResultKind.PII:
        log_pii_refusal(session_id, filter_result.pii_type or "unknown")
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        answer = pii_refusal_message(filter_result.pii_type or "personal information")
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=PII_REDACTED_PLACEHOLDER,
            answer=answer,
            refusal_category=RefusalCategory.PII.value,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=answer,
            refusal_category=RefusalCategory.PII.value,
            experience_level=experience_level,
            timings=timings,
        )

    mixed_query = filter_result.kind == FilterResultKind.MIXED

    if filter_result.kind == FilterResultKind.OUT_OF_SCOPE:
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        if is_investment_recommendation_request(question):
            answer = investment_recommendation_refusal_message()
        else:
            answer = out_of_scope_refusal_message(question)
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=answer,
            refusal_category=RefusalCategory.OUT_OF_SCOPE.value,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=answer,
            refusal_category=RefusalCategory.OUT_OF_SCOPE.value,
            experience_level=experience_level,
            timings=timings,
        )

    if filter_result.kind == FilterResultKind.NO_PERFORMANCE:
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        answer = no_performance_refusal_message(question)
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=answer,
            refusal_category=RefusalCategory.NO_PERFORMANCE.value,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=answer,
            refusal_category=RefusalCategory.NO_PERFORMANCE.value,
            experience_level=experience_level,
            timings=timings,
        )

    if state.recent_turns and is_clarification_request(question):
        clarification_result = _handle_clarification_request(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            question=question,
            mixed_query=mixed_query,
            timings=timings,
            start_total=start_total,
            serial=state.serial_explanation,
        )
        if clarification_result is not None:
            return clarification_result

    serial = state.serial_explanation
    new_topic_id = detect_serial_topic(question)
    if serial and serial.status == "active":
        if new_topic_id and new_topic_id != serial.topic_id:
            serial.status = "aborted"
            state.serial_explanation = None
            save_session_state(session_id, state)
        elif is_decline_message(question):
            state.serial_explanation = None
            save_session_state(session_id, state)
            timings.total_ms = (time.perf_counter() - start_total) * 1000
            answer = "No problem. Ask another factual question anytime."
            turn_id, _ = _record_turn(
                session_id=session_id,
                state=state,
                experience_level=experience_level,
                user_question=question,
                answer=answer,
                refusal_category=None,
                timings=timings,
            )
            return AskResult(
                turn_id=turn_id,
                session_id=session_id,
                answer=answer,
                experience_level=experience_level,
                timings=timings,
            )
        if is_continuation_message(question, serial):
            catalog = get_catalog(serial.topic_id)
            if catalog:
                section = resolve_section_for_continuation(question, serial, catalog)
                parents = load_parents_by_ids(serial.retrieved_parent_ids)
                if section and parents:
                    conversation_state = build_conversation_context(
                        session_id, state, serial.anchor_question
                    )
                    prompt_q = (
                        f"{serial.anchor_question} "
                        f"(continue — section: {section.display_title})"
                    )
                    return _deliver_serial_section(
                        session_id=session_id,
                        state=state,
                        experience_level=experience_level,
                        log_question=question,
                        prompt_question=prompt_q,
                        parents=parents,
                        catalog=catalog,
                        section=section,
                        conversation_state=conversation_state,
                        timings=timings,
                        start_total=start_total,
                        mixed_query=mixed_query,
                        rerank_used=True,
                        serial=serial,
                    )
        if state.serial_explanation is not None:
            serial.status = "aborted"
            state.serial_explanation = None
            save_session_state(session_id, state)

    topic_id = new_topic_id
    if topic_id and not state.serial_explanation:
        retrieval = retrieve(question)
        timings.embedding_ms = retrieval.timing.embed
        timings.retrieval_ms = retrieval.timing.retrieval
        timings.rerank_ms = retrieval.timing.rerank
        catalog = get_catalog(topic_id)
        if (
            catalog
            and retrieval.outcome == RetrievalOutcome.SUCCESS
            and retrieval.parents
        ):
            serial = SerialExplanationState(
                topic_id=topic_id,
                anchor_question=question,
                status="active",
                retrieved_parent_ids=[
                    p.parent_chunk_id for p in retrieval.parents
                ],
            )
            state.serial_explanation = serial
            section = catalog.sections[0]
            conversation_state = build_conversation_context(
                session_id, state, question
            )
            prompt_q = f"{question} (section: {section.display_title})"
            return _deliver_serial_section(
                session_id=session_id,
                state=state,
                experience_level=experience_level,
                log_question=question,
                prompt_question=prompt_q,
                parents=retrieval.parents,
                catalog=catalog,
                section=section,
                conversation_state=conversation_state,
                timings=timings,
                start_total=start_total,
                mixed_query=mixed_query,
                rerank_used=retrieval.rerank_used,
                serial=serial,
            )

    conversation_state = build_conversation_context(session_id, state, question)
    save_session_state(session_id, state)

    retrieval = retrieve(question)
    timings.embedding_ms = retrieval.timing.embed
    timings.retrieval_ms = retrieval.timing.retrieval
    timings.rerank_ms = retrieval.timing.rerank

    if retrieval.outcome == RetrievalOutcome.SCOPE_REFUSAL:
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=retrieval.message or "",
            refusal_category=RefusalCategory.OUT_OF_SCOPE.value,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=retrieval.message or "",
            refusal_category=RefusalCategory.OUT_OF_SCOPE.value,
            experience_level=experience_level,
            timings=timings,
        )

    if retrieval.outcome == RetrievalOutcome.CLARIFICATION:
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=retrieval.message or "",
            refusal_category=None,
            timings=timings,
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=retrieval.message or "",
            experience_level=experience_level,
            timings=timings,
        )

    if retrieval.outcome in (
        RetrievalOutcome.THIN_RETRIEVAL,
        RetrievalOutcome.NO_DATA,
    ):
        timings.total_ms = (time.perf_counter() - start_total) * 1000
        turn_id, _ = _record_turn(
            session_id=session_id,
            state=state,
            experience_level=experience_level,
            user_question=question,
            answer=retrieval.message or "",
            refusal_category=RefusalCategory.THIN_RETRIEVAL.value,
            timings=timings,
            retrieved_chunks=[],
        )
        return AskResult(
            turn_id=turn_id,
            session_id=session_id,
            answer=retrieval.message or "",
            refusal_category=RefusalCategory.THIN_RETRIEVAL.value,
            experience_level=experience_level,
            timings=timings,
        )

    parents = retrieval.parents
    sources_text = _parents_to_sources_text(parents)
    prompt = assemble_prompt(
        experience_level=experience_level,
        retrieved_sources=sources_text,
        user_question=question,
        conversation_state=conversation_state,
    )

    t0 = time.perf_counter()
    raw_output, usage = generate_completion(prompt)
    timings.generation_ms = (time.perf_counter() - t0) * 1000

    parsed = parse_citation_block(raw_output)
    body = strip_response_tags(parsed.body or raw_output)
    citation_parent = pick_citation_parent(parents, question)
    refusal_category: str | None = (
        RefusalCategory.MIXED_FACTUAL_ADVISORY.value if mixed_query else None
    )

    if is_runaway_body(body, experience_level=experience_level, question=question):
        final_answer = runaway_fallback_message(
            citation_parent.source_url, citation_parent.date_version
        )
        citation_flow = CitationFlow(
            final_outcome="runaway_fallback",
            cited_url=citation_parent.source_url,
            citation_present=True,
            url_provenance_passed=True,
        )
        raw_llm_output = raw_output
        cost_usd = estimate_cost_usd(
            embed_chars=len(question),
            rerank_docs=len(parents),
            rerank_used=retrieval.rerank_used,
        )
    else:
        regen_output: str | None = None
        first_parsed = parse_citation_block(raw_output)
        allowed_urls = {p.source_url for p in parents}
        needs_regen = (
            not first_parsed.citation_url
            or first_parsed.citation_url not in allowed_urls
        )
        if needs_regen:
            t0 = time.perf_counter()
            regen_output, regen_usage = generate_completion(
                prompt,
                extra_instruction=(
                    "Your prior answer lacked a valid citation. "
                    "Reply again with [FACTUAL] tag, answer body, "
                    "Last updated from sources line, and Source line using "
                    "ONLY URLs copied exactly from the retrieved sources above."
                ),
            )
            timings.generation_ms += (time.perf_counter() - t0) * 1000
            usage = ClaudeUsage(
                input_tokens=usage.input_tokens + regen_usage.input_tokens,
                output_tokens=usage.output_tokens + regen_usage.output_tokens,
            )

        t0 = time.perf_counter()
        final_answer, citation_flow, regen_applied = enforce_citation(
            raw_output,
            parents,
            regen_output=regen_output,
            user_question=question,
            top_rerank_score=_resolve_top_rerank_score(parents, retrieval),
            grounding_threshold=get_settings().grounding_threshold,
        )
        timings.postprocessing_ms = (time.perf_counter() - t0) * 1000
        raw_llm_output = regen_applied or raw_output
        cost_usd = estimate_cost_usd(
            embed_chars=len(question),
            rerank_docs=len(parents),
            claude_usage=usage,
            rerank_used=retrieval.rerank_used,
        )

    timings.total_ms = (time.perf_counter() - start_total) * 1000

    turn_id, _ = _record_turn(
        session_id=session_id,
        state=state,
        experience_level=experience_level,
        user_question=question,
        answer=final_answer,
        refusal_category=refusal_category,
        timings=timings,
        retrieved_chunks=_parents_to_retrieved_chunks(parents),
        final_prompt=prompt,
        raw_llm_output=raw_llm_output,
        citation_flow=citation_flow,
        cost_usd=cost_usd,
    )

    return AskResult(
        turn_id=turn_id,
        session_id=session_id,
        answer=final_answer,
        refusal_category=refusal_category,
        cited_url=citation_flow.cited_url,
        experience_level=experience_level,
        timings=timings,
        cost_usd=cost_usd,
        citation_flow=citation_flow,
        debug={"retrieval": retrieval.debug, "mixed_query": mixed_query},
    )
