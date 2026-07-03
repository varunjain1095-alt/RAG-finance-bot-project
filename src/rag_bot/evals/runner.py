"""Run Phase 5.2 live eval suite against ask() / retrieve() pipeline."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from rag_bot.config import PROJECT_ROOT, get_settings, reload_settings
from rag_bot.evals.cases import (
    ANSWER_QUALITY_CASES,
    CITATION_CONSISTENCY_QUERY,
    CITATION_CONSISTENCY_RUNS,
    EXPANSION_CASES,
    GROUNDING_GOOD_QUERIES,
    GROUNDING_THIN_QUERIES,
    MARKET_RISK_VERBATIM,
    OOS_CASES,
    PERFORMANCE_CASES,
    SCHEME_DETECTOR_CASES,
    SOURCE_OVERLAP_CASES,
    WARMTH_QUESTION,
    WARMTH_REPEAT_QUESTIONS,
)
from rag_bot.generation.filters import run_input_filters, FilterResultKind
from rag_bot.generation.logging_db import create_session
from rag_bot.generation.pipeline import ask
from rag_bot.generation.refusals import no_performance_refusal_message
from rag_bot.ingestion.db import apply_migrations, get_connection
from rag_bot.operations.regulatory import load_ui_disclaimer_snippet, market_risk_disclaimer
from rag_bot.retrieval.expansion import expand_query
from rag_bot.retrieval.pipeline import retrieve
from rag_bot.retrieval.schemes import detect_scheme
from rag_bot.retrieval.types import RetrievalOutcome, RetrievalResult

RESULTS_DIR = PROJECT_ROOT / "evals" / "results"
SWEEP_THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_result(
    passed: bool,
    query: str,
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    return {"passed": passed, "query": query, "detail": detail, **extra}


def _summarize(cases: list[dict]) -> dict[str, Any]:
    passed = sum(1 for c in cases if c["passed"])
    total = len(cases)
    return {
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "cases": cases,
    }


def check_prerequisites() -> dict[str, Any]:
    apply_migrations()
    settings = get_settings()
    with get_connection() as conn:
        child_count = conn.execute("SELECT COUNT(*) FROM child_chunks").fetchone()[0]
    return {
        "child_chunks": int(child_count),
        "anthropic_api_key_set": bool(settings.anthropic_api_key),
        "anthropic_model": settings.anthropic_model,
        "database_url": settings.database_url,
        "current_grounding_threshold": settings.grounding_threshold,
    }


def eval_scheme_detector() -> dict[str, Any]:
    cases: list[dict] = []
    for row in SCHEME_DETECTOR_CASES:
        detection = detect_scheme(row["query"])
        ok = detection.kind.value == row["expected_kind"]
        if row.get("expected_scheme"):
            actual_scheme = detection.scheme_name or detection.clarification_scheme
            ok = ok and actual_scheme == row["expected_scheme"]
        cases.append(
            _case_result(
                ok,
                row["query"],
                f"got kind={detection.kind.value} scheme={detection.scheme_name} "
                f"clarification={detection.clarification_scheme}",
                expected_kind=row["expected_kind"],
                expected_scheme=row.get("expected_scheme"),
            )
        )
    return _summarize(cases)


def eval_query_expansion() -> dict[str, Any]:
    cases: list[dict] = []
    for row in EXPANSION_CASES:
        expanded = expand_query(row["query"])
        retrieval = retrieve(row["query"])
        lexical_ok = expanded.lexical_expanded == row["lexical_expanded"]
        semantic_longer = len(expanded.semantic_query) > len(row["query"])
        semantic_ok = (
            expanded.semantic_query != row["query"]
            if row["semantic_has_extra"]
            else expanded.semantic_query == row["query"]
        )
        ok = lexical_ok and semantic_ok
        cases.append(
            _case_result(
                ok,
                row["query"],
                f"lexical_expanded={expanded.lexical_expanded} "
                f"semantic_len={len(expanded.semantic_query)} "
                f"retrieval_outcome={retrieval.outcome.value}",
                lexical_expanded=expanded.lexical_expanded,
                semantic_query=expanded.semantic_query,
                lexical_query=expanded.lexical_query,
            )
        )
    return _summarize(cases)


def _filter_refusal_kind(refusal_key: str) -> FilterResultKind:
    if refusal_key == "out_of_scope":
        return FilterResultKind.OUT_OF_SCOPE
    return FilterResultKind.NO_PERFORMANCE


def _safe_ask(session_id, query: str) -> tuple[Any | None, str | None]:
    try:
        return ask(session_id, query), None
    except Exception as exc:
        return None, str(exc)


def _keywords_ok(answer_lower: str, row: dict) -> bool:
    groups = row.get("keyword_groups")
    if groups:
        return any(
            all(k.lower() in answer_lower for k in group) for group in groups
        )
    keywords = row.get("keywords", [])
    return all(k.lower() in answer_lower for k in keywords)


def _chat_refusal_eval(cases: list[dict], refusal_key: str) -> dict[str, Any]:
    session_id = create_session(experience_level="somewhat_familiar")
    filter_kind = _filter_refusal_kind(refusal_key)
    results: list[dict] = []
    for row in cases:
        fr = run_input_filters(row["query"])
        if row["expect_refusal"]:
            if fr.kind == filter_kind:
                ok = True
                detail = f"filter={fr.kind.value}"
            else:
                result, err = _safe_ask(session_id, row["query"])
                if err:
                    ok = False
                    detail = f"ask_error={err}"
                else:
                    ok = result.refusal_category == refusal_key
                    detail = f"refusal_category={result.refusal_category}"
        else:
            if fr.kind == filter_kind:
                ok = False
                detail = f"false positive filter={fr.kind.value}"
            elif fr.kind == FilterResultKind.PII:
                ok = False
                detail = "unexpected PII filter"
            else:
                result, err = _safe_ask(session_id, row["query"])
                if err:
                    ok = False
                    detail = f"ask_error={err}"
                else:
                    ok = result.refusal_category != refusal_key
                    detail = f"refusal_category={result.refusal_category}"
        results.append(_case_result(ok, row["query"], detail))
    return _summarize(results)


def eval_out_of_scope() -> dict[str, Any]:
    return _chat_refusal_eval(OOS_CASES, "out_of_scope")


def eval_no_performance() -> dict[str, Any]:
    return _chat_refusal_eval(PERFORMANCE_CASES, "no_performance")


def eval_selective_warmth() -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "passed": 0,
            "failed": 1,
            "total": 1,
            "pass_rate": 0.0,
            "skipped": True,
            "reason": "ANTHROPIC_API_KEY not set",
            "cases": [],
        }

    beginner_id = create_session(experience_level="new")
    expert_id = create_session(experience_level="expert")

    beginner_main, err = _safe_ask(beginner_id, WARMTH_QUESTION)
    expert_main, err2 = _safe_ask(expert_id, WARMTH_QUESTION)
    if err or err2 or beginner_main is None or expert_main is None:
        return {
            "passed": 0,
            "failed": 4,
            "total": 4,
            "pass_rate": 0.0,
            "error": err or err2,
            "cases": [],
        }

    beginner_answers: list[str] = []
    for q in WARMTH_REPEAT_QUESTIONS:
        r, err = _safe_ask(beginner_id, q)
        if err or r is None:
            beginner_answers.append("")
        else:
            beginner_answers.append(r.answer.lower())

    cases: list[dict] = []

    # Beginner should use plain-language cues (parentheses or brief definitions)
    beginner_has_context = (
        "(" in beginner_main.answer
        or "which is" in beginner_main.answer.lower()
        or "means" in beginner_main.answer.lower()
    )
    cases.append(
        _case_result(
            beginner_has_context,
            WARMTH_QUESTION,
            "beginner contextual explanation",
            level="new",
            answer_snippet=beginner_main.answer[:200],
        )
    )

    # Expert should avoid cheerleading
    expert_no_cheer = "great question" not in expert_main.answer.lower()
    cases.append(
        _case_result(
            expert_no_cheer,
            WARMTH_QUESTION,
            "expert avoids cheerleading",
            level="expert",
            answer_snippet=expert_main.answer[:200],
        )
    )

    # Expert typically shorter than beginner for same question
    expert_shorter = len(expert_main.answer) <= len(beginner_main.answer) * 1.2
    cases.append(
        _case_result(
            expert_shorter,
            WARMTH_QUESTION,
            f"expert_len={len(expert_main.answer)} beginner_len={len(beginner_main.answer)}",
        )
    )

    great_question_count = sum(1 for a in beginner_answers if "great question" in a)
    no_repetitive_praise = great_question_count <= 1
    cases.append(
        _case_result(
            no_repetitive_praise,
            "repeated beginner questions",
            f"great_question_count={great_question_count}",
        )
    )

    return _summarize(cases)


def _retrieve_at_threshold(query: str, threshold: float) -> RetrievalResult:
    settings = get_settings().model_copy(update={"grounding_threshold": threshold})
    with patch("rag_bot.config.get_settings", return_value=settings):
        return retrieve(query)


def eval_grounding_sweep() -> dict[str, Any]:
    sweep_rows: list[dict] = []
    best_threshold = 0.35
    best_score = -1.0

    for threshold in SWEEP_THRESHOLDS:
        good_pass = 0
        thin_refuse = 0

        for q in GROUNDING_GOOD_QUERIES:
            r = _retrieve_at_threshold(q, threshold)
            if r.outcome == RetrievalOutcome.SUCCESS:
                good_pass += 1

        for q in GROUNDING_THIN_QUERIES:
            r = _retrieve_at_threshold(q, threshold)
            if r.outcome in (
                RetrievalOutcome.THIN_RETRIEVAL,
                RetrievalOutcome.NO_DATA,
                RetrievalOutcome.SCOPE_REFUSAL,
            ):
                thin_refuse += 1

        good_rate = good_pass / len(GROUNDING_GOOD_QUERIES)
        thin_rate = thin_refuse / len(GROUNDING_THIN_QUERIES)
        balance = 0.6 * good_rate + 0.4 * thin_rate
        sweep_rows.append(
            {
                "threshold": threshold,
                "good_pass": good_pass,
                "good_total": len(GROUNDING_GOOD_QUERIES),
                "good_rate": round(good_rate, 4),
                "thin_refuse": thin_refuse,
                "thin_total": len(GROUNDING_THIN_QUERIES),
                "thin_rate": round(thin_rate, 4),
                "balance_score": round(balance, 4),
            }
        )
        if balance > best_score:
            best_score = balance
            best_threshold = threshold
        elif abs(balance - best_score) < 1e-9:
            # When thin-query refusal does not discriminate, prefer context default.
            if abs(threshold - 0.35) < abs(best_threshold - 0.35):
                best_threshold = threshold

    return {
        "recommended_threshold": best_threshold,
        "best_balance_score": best_score,
        "sweep": sweep_rows,
        "passed": 1 if best_score > 0 else 0,
        "failed": 0 if best_score > 0 else 1,
        "total": 1,
        "pass_rate": 1.0 if best_score > 0 else 0.0,
        "cases": [{"passed": True, "detail": f"recommended={best_threshold}"}],
    }


def update_env_grounding_threshold(value: float) -> None:
    env_path = PROJECT_ROOT / ".env"
    line = f"GROUNDING_THRESHOLD={value}"
    if env_path.is_file():
        content = env_path.read_text(encoding="utf-8")
        if re.search(r"^GROUNDING_THRESHOLD=", content, re.MULTILINE):
            content = re.sub(
                r"^GROUNDING_THRESHOLD=.*$",
                line,
                content,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            content = content.rstrip() + "\n" + line + "\n"
        env_path.write_text(content, encoding="utf-8")
    else:
        env_path.write_text(line + "\n", encoding="utf-8")
    reload_settings()


def eval_citation_consistency() -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "passed": 0,
            "failed": 1,
            "total": 1,
            "pass_rate": 0.0,
            "skipped": True,
            "reason": "ANTHROPIC_API_KEY not set",
            "cases": [],
        }

    session_id = create_session(experience_level="somewhat_familiar")
    urls: list[str | None] = []
    cases: list[dict] = []
    for i in range(CITATION_CONSISTENCY_RUNS):
        result, err = _safe_ask(session_id, CITATION_CONSISTENCY_QUERY)
        if err or result is None:
            cases.append(_case_result(False, f"run {i + 1}", f"ask_error={err}"))
            urls.append(None)
            continue
        urls.append(result.cited_url)
        cases.append(
            _case_result(
                result.cited_url is not None,
                f"run {i + 1}",
                f"cited_url={result.cited_url}",
            )
        )

    non_null = [u for u in urls if u]
    consistent = len(non_null) > 0 and len(set(non_null)) == 1
    cases.append(
        _case_result(
            consistent,
            "consistency check",
            f"urls={non_null}",
        )
    )
    summary = _summarize(cases)
    summary["unique_citations"] = list(set(non_null))
    return summary


def eval_source_overlap() -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "passed": 0,
            "failed": len(SOURCE_OVERLAP_CASES),
            "total": len(SOURCE_OVERLAP_CASES),
            "pass_rate": 0.0,
            "skipped": True,
            "reason": "ANTHROPIC_API_KEY not set",
            "cases": [],
        }

    session_id = create_session(experience_level="somewhat_familiar")
    cases: list[dict] = []
    for row in SOURCE_OVERLAP_CASES:
        result, err = _safe_ask(session_id, row["query"])
        if err or result is None:
            cases.append(
                _case_result(False, row["query"], f"ask_error={err}", note=row["note"])
            )
            continue
        url = (result.cited_url or "").lower()
        ok = result.cited_url is not None and any(
            part in url for part in row["url_must_contain"]
        )
        cases.append(
            _case_result(
                ok,
                row["query"],
                f"cited_url={result.cited_url} note={row['note']}",
            )
        )
    return _summarize(cases)


def eval_answer_quality() -> dict[str, Any]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "passed": 0,
            "failed": len(ANSWER_QUALITY_CASES),
            "total": len(ANSWER_QUALITY_CASES),
            "pass_rate": 0.0,
            "skipped": True,
            "reason": "ANTHROPIC_API_KEY not set",
            "cases": [],
        }

    cases: list[dict] = []
    for row in ANSWER_QUALITY_CASES:
        eval_type = row["eval_type"]
        session_id = create_session(experience_level="somewhat_familiar")
        if eval_type == "multiturn":
            _, setup_err = _safe_ask(session_id, row["setup_query"])
            if setup_err:
                cases.append(
                    _case_result(
                        False,
                        row["query"],
                        f"setup_error={setup_err}",
                        id=row.get("id"),
                        eval_type=eval_type,
                    )
                )
                continue
        result, err = _safe_ask(session_id, row["query"])
        if err or result is None:
            cases.append(
                _case_result(
                    False,
                    row["query"],
                    f"ask_error={err}",
                    id=row.get("id"),
                    eval_type=eval_type,
                )
            )
            continue
        answer_lower = result.answer.lower()

        if eval_type == "factual":
            keywords_ok = _keywords_ok(answer_lower, row)
            citation_ok = result.cited_url is not None and result.refusal_category is None
            ok = keywords_ok and citation_ok
            detail = f"keywords_ok={keywords_ok} citation={result.cited_url}"
        elif eval_type == "refusal":
            ok = result.refusal_category == row["refusal_category"]
            detail = f"refusal_category={result.refusal_category}"
        elif eval_type == "experience":
            keywords_ok = _keywords_ok(answer_lower, row)
            ok = keywords_ok and result.refusal_category is None
            detail = f"keywords_ok={keywords_ok}"
        elif eval_type == "mixed":
            keywords_ok = _keywords_ok(answer_lower, row)
            category_ok = result.refusal_category == row["refusal_category"]
            citation_ok = result.cited_url is not None
            ok = keywords_ok and category_ok and citation_ok
            detail = (
                f"keywords_ok={keywords_ok} category={result.refusal_category} "
                f"citation={result.cited_url}"
            )
        elif eval_type == "multiturn":
            keywords_ok = _keywords_ok(answer_lower, row)
            citation_ok = result.cited_url is not None and result.refusal_category is None
            ok = keywords_ok and citation_ok
            detail = f"keywords_ok={keywords_ok} citation={result.cited_url}"
        else:
            ok = False
            detail = f"unknown eval_type={eval_type}"

        cases.append(
            _case_result(
                ok,
                row["query"],
                detail,
                id=row.get("id"),
                eval_type=eval_type,
                refusal_category=result.refusal_category,
                answer_snippet=result.answer[:400],
            )
        )
    return _summarize(cases)


def eval_regulatory_verbatim() -> dict[str, Any]:
    cases: list[dict] = []

    ui = load_ui_disclaimer_snippet()
    cases.append(
        _case_result(
            MARKET_RISK_VERBATIM in ui,
            "ui_disclaimer_snippet.md",
            "template contains verbatim market-risk disclaimer",
        )
    )

    perf_msg = no_performance_refusal_message("What is the 5-year CAGR of Bluechip?")
    cases.append(
        _case_result(
            MARKET_RISK_VERBATIM in perf_msg,
            "live performance refusal",
            "no_performance_refusal_message includes verbatim disclaimer",
        )
    )
    cases.append(
        _case_result(
            market_risk_disclaimer() == MARKET_RISK_VERBATIM,
            "regulatory loader",
            "market_risk_disclaimer() matches verbatim text",
        )
    )

    settings = get_settings()
    if settings.anthropic_api_key:
        session_id = create_session(experience_level="somewhat_familiar")
        live, err = _safe_ask(session_id, "What is the 5-year return of Flexicap?")
        cases.append(
            _case_result(
                live is not None
                and not err
                and MARKET_RISK_VERBATIM in live.answer,
                "live /chat performance refusal",
                f"refusal_category={live.refusal_category if live else None} error={err}",
            )
        )
    else:
        cases.append(
            _case_result(
                False,
                "live /chat performance refusal",
                "skipped — ANTHROPIC_API_KEY not set",
            )
        )

    learnings_path = PROJECT_ROOT / "templates" / "learnings_document_disclaimer.md"
    learnings_text = learnings_path.read_text(encoding="utf-8")
    cases.append(
        _case_result(
            MARKET_RISK_VERBATIM in learnings_text,
            "learnings_document_disclaimer.md",
            "learnings disclaimer contains verbatim market-risk text",
        )
    )

    return _summarize(cases)


def run_eval_suite(
    *,
    apply_threshold: bool = True,
    skip_llm: bool = False,
) -> dict[str, Any]:
    """Run all 10 Phase 5.2 evals; write results to evals/results/."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prereq = check_prerequisites()
    if prereq["child_chunks"] < 100:
        raise RuntimeError(
            f"Corpus too small for live evals (child_chunks={prereq['child_chunks']}). "
            "Run ingest first."
        )

    if skip_llm and not prereq["anthropic_api_key_set"]:
        skip_llm = True

    started = _now_iso()
    results: dict[str, Any] = {
        "started_at": started,
        "prerequisites": prereq,
        "evals": {},
    }

    runners: list[tuple[str, callable]] = [
        ("5.2.1_scheme_detector", eval_scheme_detector),
        ("5.2.2_query_expansion", eval_query_expansion),
        ("5.2.3_out_of_scope", eval_out_of_scope),
        ("5.2.4_no_performance", eval_no_performance),
    ]

    if not skip_llm:
        runners.extend(
            [
                ("5.2.5_selective_warmth", eval_selective_warmth),
            ]
        )
    else:
        results["evals"]["5.2.5_selective_warmth"] = {
            "skipped": True,
            "reason": "skip_llm or no API key",
            "passed": 0,
            "failed": 0,
            "total": 0,
            "pass_rate": None,
        }

    runners.append(("5.2.6_grounding_threshold_sweep", eval_grounding_sweep))

    if not skip_llm:
        runners.extend(
            [
                ("5.2.7_citation_consistency", eval_citation_consistency),
                ("5.2.8_source_overlap", eval_source_overlap),
                ("5.2.9_answer_quality", eval_answer_quality),
            ]
        )
    else:
        for key in (
            "5.2.7_citation_consistency",
            "5.2.8_source_overlap",
            "5.2.9_answer_quality",
        ):
            results["evals"][key] = {
                "skipped": True,
                "reason": "skip_llm or no API key",
                "passed": 0,
                "failed": 0,
                "total": 0,
                "pass_rate": None,
            }

    runners.append(("5.2.10_regulatory_verbatim", eval_regulatory_verbatim))

    for name, fn in runners:
        if name in results["evals"]:
            continue
        try:
            results["evals"][name] = fn()
        except Exception as exc:
            results["evals"][name] = {
                "passed": 0,
                "failed": 1,
                "total": 1,
                "pass_rate": 0.0,
                "error": str(exc),
                "cases": [],
            }

    sweep = results["evals"].get("5.2.6_grounding_threshold_sweep", {})
    recommended = sweep.get("recommended_threshold")
    if apply_threshold and recommended is not None:
        update_env_grounding_threshold(float(recommended))
        results["grounding_threshold_applied"] = float(recommended)
    else:
        results["grounding_threshold_applied"] = None

    reload_settings()
    results["finished_at"] = _now_iso()
    results["final_grounding_threshold"] = get_settings().grounding_threshold

    total_passed = 0
    total_failed = 0
    for ev in results["evals"].values():
        if ev.get("skipped"):
            continue
        total_passed += ev.get("passed", 0)
        total_failed += ev.get("failed", 0)
    results["aggregate"] = {
        "passed": total_passed,
        "failed": total_failed,
        "total": total_passed + total_failed,
        "pass_rate": round(total_passed / (total_passed + total_failed), 4)
        if (total_passed + total_failed)
        else 0.0,
    }

    (RESULTS_DIR / "summary.json").write_text(
        json.dumps(results, indent=2, default=str),
        encoding="utf-8",
    )
    _write_summary_md(results)
    return results


def _write_summary_md(results: dict[str, Any]) -> None:
    lines = [
        "# Phase 5.2 live eval results",
        "",
        f"Started: {results['started_at']}",
        f"Finished: {results.get('finished_at')}",
        "",
        f"**Anthropic model:** {results['prerequisites'].get('anthropic_model')}",
        "",
        "## Aggregate",
        "",
        f"- Passed: {results['aggregate']['passed']}",
        f"- Failed: {results['aggregate']['failed']}",
        f"- Pass rate: {results['aggregate']['pass_rate']}",
        "",
        "## Per eval",
        "",
        "| Eval | Passed | Failed | Total | Pass rate |",
        "|------|--------|--------|-------|-----------|",
    ]
    for name, ev in results["evals"].items():
        if ev.get("skipped"):
            lines.append(f"| {name} | — | — | — | SKIPPED |")
        else:
            lines.append(
                f"| {name} | {ev.get('passed', 0)} | {ev.get('failed', 0)} | "
                f"{ev.get('total', 0)} | {ev.get('pass_rate', 0)} |"
            )
    lines.append("")
    sweep = results["evals"].get("5.2.6_grounding_threshold_sweep", {})
    if sweep.get("sweep"):
        lines.append("## Grounding threshold sweep")
        lines.append("")
        for row in sweep["sweep"]:
            lines.append(
                f"- `{row['threshold']}`: good={row['good_rate']} "
                f"thin={row['thin_rate']} balance={row['balance_score']}"
            )
        lines.append("")
        lines.append(f"**Recommended:** {sweep.get('recommended_threshold')}")
    (RESULTS_DIR / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    for name, ev in results["evals"].items():
        (RESULTS_DIR / f"{name}.json").write_text(
            json.dumps(ev, indent=2, default=str),
            encoding="utf-8",
        )
