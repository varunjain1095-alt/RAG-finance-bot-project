"""End-to-end retrieval pipeline (Phase 2 — no LLM generation)."""

import logging
import time

from rag_bot.ingestion.db import get_connection
from rag_bot.ingestion.embeddings import embed_texts
from rag_bot.retrieval.grounding import evaluate_grounding_threshold
from rag_bot.retrieval.expansion import expand_query
from rag_bot.retrieval.parents import dedupe_by_parent, swap_to_parents
from rag_bot.retrieval.rerank import rerank_candidates
from rag_bot.retrieval.refusals import (
    clarification_message,
    no_data_for_scheme_message,
    scope_refusal_message,
    thin_retrieval_message,
)
from rag_bot.retrieval.schemes import SchemeDetectionKind, detect_scheme
from rag_bot.retrieval.search import hybrid_search
from rag_bot.retrieval.types import RetrievalOutcome, RetrievalResult, TimingMs
from rag_bot.config import get_settings

logger = logging.getLogger(__name__)


def retrieve(query: str) -> RetrievalResult:
    """Run full retrieval path: detect → expand → embed → hybrid → rerank → parent swap."""
    settings = get_settings()
    timing = TimingMs()
    start_total = time.perf_counter()
    debug: dict = {}

    t0 = time.perf_counter()
    detection = detect_scheme(query)
    timing.scheme_detection = (time.perf_counter() - t0) * 1000
    debug["scheme_detection"] = detection.kind.value

    if detection.kind == SchemeDetectionKind.OUT_OF_SCOPE:
        timing.total = (time.perf_counter() - start_total) * 1000
        return RetrievalResult(
            outcome=RetrievalOutcome.SCOPE_REFUSAL,
            query=query,
            message=scope_refusal_message(detection.out_of_scope_label),
            detected_scheme=detection.scheme_name,
            rerank_used=False,
            timing=timing,
            debug=debug,
        )

    if detection.kind == SchemeDetectionKind.CLARIFICATION:
        timing.total = (time.perf_counter() - start_total) * 1000
        return RetrievalResult(
            outcome=RetrievalOutcome.CLARIFICATION,
            query=query,
            message=clarification_message(detection.clarification_scheme or ""),
            rerank_used=False,
            timing=timing,
            debug=debug,
        )

    scheme_filter = (
        detection.scheme_name
        if detection.kind == SchemeDetectionKind.MATCHED
        else None
    )
    debug["scheme_filter"] = scheme_filter

    t0 = time.perf_counter()
    expanded = expand_query(query)
    timing.expansion = (time.perf_counter() - t0) * 1000
    debug["semantic_query"] = expanded.semantic_query
    debug["lexical_query"] = expanded.lexical_query
    debug["lexical_expanded"] = expanded.lexical_expanded

    t0 = time.perf_counter()
    query_embedding = embed_texts([expanded.semantic_query])[0]
    timing.embed = (time.perf_counter() - t0) * 1000

    with get_connection() as conn:
        t0 = time.perf_counter()
        candidates = hybrid_search(
            conn,
            query_embedding,
            expanded.lexical_query,
            scheme_name=scheme_filter,
            top_k=settings.retrieval_top_k,
        )
        timing.retrieval = (time.perf_counter() - t0) * 1000
        debug["rrf_candidate_count"] = len(candidates)

        if not candidates:
            timing.total = (time.perf_counter() - start_total) * 1000
            if scheme_filter:
                return RetrievalResult(
                    outcome=RetrievalOutcome.NO_DATA,
                    query=query,
                    message=no_data_for_scheme_message(scheme_filter),
                    detected_scheme=scheme_filter,
                    rerank_used=False,
                    timing=timing,
                    debug=debug,
                )
            return RetrievalResult(
                outcome=RetrievalOutcome.THIN_RETRIEVAL,
                query=query,
                message=thin_retrieval_message(),
                rerank_used=False,
                timing=timing,
                debug=debug,
            )

        t0 = time.perf_counter()
        reranked, rerank_used, _rerank_top_score = rerank_candidates(
            query, candidates, top_k=settings.retrieval_top_k
        )
        timing.rerank = (time.perf_counter() - t0) * 1000
        debug["rerank_used"] = rerank_used
        if _rerank_top_score is not None:
            debug["top_rerank_score"] = _rerank_top_score

        passes, grounding_score, grounding_source = evaluate_grounding_threshold(
            reranked, settings.grounding_threshold
        )
        debug["grounding_score"] = grounding_score
        debug["grounding_score_source"] = grounding_source

        if not passes:
            timing.total = (time.perf_counter() - start_total) * 1000
            return RetrievalResult(
                outcome=RetrievalOutcome.THIN_RETRIEVAL,
                query=query,
                message=thin_retrieval_message(),
                detected_scheme=scheme_filter,
                top_rerank_score=grounding_score,
                rerank_used=rerank_used,
                timing=timing,
                debug=debug,
            )

        t0 = time.perf_counter()
        unique_children = dedupe_by_parent(
            reranked, max_parents=settings.retrieval_top_parents
        )
        parents = swap_to_parents(conn, unique_children)
        timing.assembly = (time.perf_counter() - t0) * 1000

    timing.total = (time.perf_counter() - start_total) * 1000
    return RetrievalResult(
        outcome=RetrievalOutcome.SUCCESS,
        query=query,
        parents=parents,
        detected_scheme=scheme_filter,
        top_rerank_score=grounding_score,
        rerank_used=rerank_used,
        timing=timing,
        debug=debug,
    )
