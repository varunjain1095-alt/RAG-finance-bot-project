"""On-demand post-chat learnings PDF generation."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

from rag_bot.config import PROJECT_ROOT, get_settings
from rag_bot.generation.citations import parse_citation_block
from rag_bot.generation.llm import ClaudeUsage, generate_completion
from rag_bot.generation.logging_db import (
    ensure_session_active,
    fetch_session_turns,
    mark_learnings_generated,
)

logger = logging.getLogger(__name__)

DISCLAIMER_PATH = PROJECT_ROOT / "templates" / "learnings_document_disclaimer.md"
LEARNINGS_ROOT = PROJECT_ROOT / "data" / "learnings"

_SUBSTANTIVE_WORD_RE = re.compile(r"[a-z0-9]{4,}", re.I)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def _read_disclaimer() -> tuple[str, str]:
    text = DISCLAIMER_PATH.read_text(encoding="utf-8")
    parts = text.split("---", maxsplit=1)
    brief = parts[0].strip()
    full = parts[1].strip() if len(parts) > 1 else brief
    return brief, full


def _collect_sources(turns: list[dict]) -> list[str]:
    urls: list[str] = []
    for turn in turns:
        flow = turn.get("citation_flow") or {}
        cited = flow.get("cited_url")
        if cited and cited not in urls:
            urls.append(cited)
        parsed = parse_citation_block(turn["final_answer"])
        if parsed.citation_url and parsed.citation_url not in urls:
            urls.append(parsed.citation_url)
    return urls


def _collect_refusals(turns: list[dict]) -> list[str]:
    lines: list[str] = []
    for turn in turns:
        category = turn.get("refusal_category")
        if not category:
            continue
        question = turn["user_question"]
        if category == "no_performance":
            lines.append(
                f"I asked about performance or returns (\"{question}\"); "
                "the bot redirected to the factsheet."
            )
        elif category == "out_of_scope":
            lines.append(
                f"I asked for advice (\"{question}\"); "
                "the bot explained it provides facts only."
            )
        elif category == "pii":
            lines.append("A message contained personal information and was refused.")
        elif category == "thin_retrieval":
            lines.append(
                f"The bot could not find a clear answer for \"{question}\"."
            )
        elif category == "mixed_factual_advisory":
            lines.append(
                f"Mixed factual + advisory question (\"{question}\"); "
                "the bot answered facts and declined advice."
            )
        else:
            lines.append(f"Refusal ({category}): \"{question}\"")
    return lines


def _factual_answer_turns(turns: list[dict]) -> list[dict]:
    return [t for t in turns if not t.get("refusal_category")]


def _build_key_facts_prompt(answers: list[str]) -> str:
    joined = "\n\n---\n\n".join(answers)
    return (
        "Extract factual claims from these bot answers from a single chat session. "
        "Group facts by scheme, then by topic (expense ratio, exit load, etc.). "
        "For numbers, dates, and scheme rules use the EXACT wording from the answers. "
        "Only add minimal connecting words for readability. "
        "Preserve citation URLs next to the facts they support. "
        "Do not add facts that are not present in the answers.\n\n"
        f"ANSWERS:\n{joined}"
    )


def substantive_overlap_ok(extracted_line: str, source_answers: list[str]) -> bool:
    """Coarse word-overlap check — substantive tokens must appear in source answers."""
    corpus = " ".join(source_answers).lower()
    tokens = _SUBSTANTIVE_WORD_RE.findall(extracted_line)
    if tokens:
        matched = sum(1 for token in tokens if token.lower() in corpus)
        if matched / len(tokens) < 0.6:
            return False
    numbers = _NUMBER_RE.findall(extracted_line)
    if numbers:
        return all(number in corpus for number in numbers)
    return True


def filter_key_facts(key_facts_text: str, source_answers: list[str]) -> str:
    kept: list[str] = []
    for line in key_facts_text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if stripped.startswith("#"):
            kept.append(stripped)
            continue
        if stripped.startswith("-") or stripped.startswith("*"):
            if substantive_overlap_ok(stripped, source_answers):
                kept.append(stripped)
            else:
                logger.warning("Dropped learnings line failing overlap check: %s", stripped)
        else:
            kept.append(stripped)
    return "\n".join(kept).strip()


def generate_key_facts_section(answers: list[str]) -> tuple[str, ClaudeUsage | None]:
    if not answers:
        return "No factual answers in this session yet.", None
    prompt = _build_key_facts_prompt(answers)
    text, usage = generate_completion(prompt, max_tokens=1500)
    filtered = filter_key_facts(text, answers)
    return filtered or "No extractable factual claims found.", usage


class LearningsPDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 10, "Your conversation with the ICICI Pru FAQ bot", ln=True)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        self.ln(2)


def _pdf_safe(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _write_section(pdf: FPDF, title: str, body: str) -> None:
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe(title), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _pdf_safe(body))
    pdf.ln(3)


def build_learnings_pdf(
    session_id: uuid.UUID,
    *,
    key_facts: str,
    turns: list[dict],
    brief_disclaimer: str,
    full_disclaimer: str,
) -> bytes:
    pdf = LearningsPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _write_section(pdf, "Disclaimer (brief)", brief_disclaimer)
    _write_section(pdf, "Key facts you learned", key_facts)

    transcript_lines: list[str] = []
    for turn in turns:
        transcript_lines.append(f"Q: {turn['user_question']}")
        transcript_lines.append(f"A: {turn['final_answer']}")
        transcript_lines.append("")
    _write_section(pdf, "Conversation transcript", "\n".join(transcript_lines).strip())

    sources = _collect_sources(turns)
    _write_section(
        pdf,
        "Sources referenced",
        "\n".join(sources) if sources else "No citations recorded in this session.",
    )

    refusals = _collect_refusals(turns)
    _write_section(
        pdf,
        "What wasn't covered",
        "\n".join(refusals) if refusals else "No refusals in this session.",
    )

    _write_section(pdf, "Full disclaimer", full_disclaimer)

    return bytes(pdf.output())


def learnings_pdf_path(session_id: uuid.UUID) -> Path:
    return LEARNINGS_ROOT / str(session_id) / "document.pdf"


def cleanup_stale_learnings() -> int:
    settings = get_settings()
    if not LEARNINGS_ROOT.is_dir():
        return 0
    removed = 0
    now = datetime.now(timezone.utc).timestamp()
    for session_dir in LEARNINGS_ROOT.iterdir():
        if not session_dir.is_dir():
            continue
        pdf_path = session_dir / "document.pdf"
        if not pdf_path.is_file():
            continue
        age = now - pdf_path.stat().st_mtime
        if age > settings.learnings_retention_seconds:
            pdf_path.unlink(missing_ok=True)
            try:
                session_dir.rmdir()
            except OSError:
                pass
            removed += 1
    return removed


def generate_learnings_document(session_id: uuid.UUID) -> Path:
    cleanup_stale_learnings()
    ensure_session_active(session_id)
    turns = fetch_session_turns(session_id)
    brief_disclaimer, full_disclaimer = _read_disclaimer()

    factual = _factual_answer_turns(turns)
    answers = [t["final_answer"] for t in factual]
    key_facts, _ = generate_key_facts_section(answers)

    pdf_bytes = build_learnings_pdf(
        session_id,
        key_facts=key_facts,
        turns=turns,
        brief_disclaimer=brief_disclaimer,
        full_disclaimer=full_disclaimer,
    )

    out_path = learnings_pdf_path(session_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pdf_bytes)
    mark_learnings_generated(session_id)
    logger.info("Learnings PDF written to %s", out_path)
    return out_path


def get_learnings_pdf_if_fresh(session_id: uuid.UUID) -> Path | None:
    cleanup_stale_learnings()
    path = learnings_pdf_path(session_id)
    if not path.is_file():
        return None
    settings = get_settings()
    age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    if age > settings.learnings_retention_seconds:
        path.unlink(missing_ok=True)
        return None
    return path
