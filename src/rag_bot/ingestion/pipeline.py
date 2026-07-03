"""Ingestion pipeline orchestration."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rag_bot.ingestion.chunking import chunk_markdown, count_tokens
from rag_bot.ingestion.db import (
    apply_migrations,
    clear_corpus,
    delete_chunks_for_document,
    get_connection,
    get_document_stats,
    get_latest_document_id,
    get_parsed_text,
    insert_chunks,
    insert_document,
)
from rag_bot.ingestion.embeddings import embed_texts
from rag_bot.ingestion.fetch import fetch_url
from rag_bot.ingestion.parsers.html import parse_html
from rag_bot.ingestion.parsers.pdf import parse_pdf
from rag_bot.ingestion.parsers.combined_factsheet import chunk_combined_factsheet_markdown
from rag_bot.ingestion.parsers.faqs_md import load_faqs_sections
from rag_bot.ingestion.parsers.ter_csv import ter_parent_chunk
from rag_bot.ingestion.sources import SourceEntry, load_sources_from_markdown

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ParseStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class DocumentResult:
    entry: SourceEntry
    status: ParseStatus
    char_count: int = 0
    parent_count: int = 0
    child_count: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _is_pdf(url: str, content_type: str | None) -> bool:
    if url.lower().endswith(".pdf"):
        return True
    if content_type and "pdf" in content_type.lower():
        return True
    return False


def _chunk_entry_markdown(entry: SourceEntry, markdown: str) -> list:
    if entry.combined_factsheet:
        return chunk_combined_factsheet_markdown(markdown)
    return chunk_markdown(markdown)


def _parse_content(content: bytes, url: str, content_type: str | None) -> tuple[str, list[str]]:
    if _is_pdf(url, content_type):
        return parse_pdf(content)
    return parse_html(content, url)


def _classify_status(
    markdown: str,
    warnings: list[str],
    child_count: int,
    *,
    structured_tabular: bool = False,
) -> ParseStatus:
    if not markdown.strip() or child_count == 0:
        return ParseStatus.FAILED
    if structured_tabular:
        return ParseStatus.PARTIAL if warnings else ParseStatus.SUCCESS
    if warnings or count_tokens(markdown) < 300:
        return ParseStatus.PARTIAL
    return ParseStatus.SUCCESS


def _ingest_local_entry(conn, entry: SourceEntry) -> DocumentResult:
    result = DocumentResult(entry=entry, status=ParseStatus.FAILED)
    if not entry.local_path:
        result.error = "local_path missing on corpus entry"
        return result

    local_file = PROJECT_ROOT / entry.local_path
    if not local_file.is_file():
        result.error = f"Local file not found: {local_file}"
        return result

    logger.info("Loading local corpus file %s", local_file)

    warnings: list[str] = []
    parents: list = []

    if entry.ter_csv_scheme:
        parents = [ter_parent_chunk(local_file, entry.ter_csv_scheme)]
        markdown = parents[0].text
    elif local_file.suffix.lower() == ".md":
        markdown = local_file.read_text(encoding="utf-8")
        for citation_url, heading, body in load_faqs_sections(local_file):
            for parent in chunk_markdown(body):
                parent.citation_url = citation_url
                if heading:
                    parent.section_heading = heading
                parents.append(parent)
        if not parents:
            warnings.append("No citation-delimited FAQ sections parsed")
    else:
        result.error = f"Unsupported local file type: {local_file.suffix}"
        return result

    result.warnings = warnings
    result.char_count = len(markdown)
    result.parent_count = len(parents)

    embed_inputs: list[str] = []
    for parent in parents:
        prepend_scheme = parent.scheme_name or entry.scheme_name or ""
        for child in parent.children:
            embed_inputs.append(
                f"{prepend_scheme} | {child.section_heading}\n{child.text}".strip()
            )

    embeddings = embed_texts(embed_inputs) if embed_inputs else []
    result.child_count = len(embeddings)
    result.status = _classify_status(
        markdown, warnings, result.child_count, structured_tabular=entry.structured_tabular
    )

    if result.status == ParseStatus.FAILED:
        result.error = "No extractable text or zero chunks"
        logger.warning("Skipped %s: %s", entry.source_name, result.error)
        return result

    document_id = insert_document(conn, entry, markdown)
    insert_chunks(conn, document_id, entry, parents, embeddings)
    conn.commit()
    logger.info(
        "Ingested local %s: %s (%d parents, %d children)",
        result.status.value,
        entry.source_name,
        result.parent_count,
        result.child_count,
    )
    return result


def _ingest_single_entry(conn, entry: SourceEntry) -> DocumentResult:
    if entry.local_path:
        return _ingest_local_entry(conn, entry)

    result = DocumentResult(entry=entry, status=ParseStatus.FAILED)
    logger.info("Fetching %s", entry.source_url)
    content, content_type = fetch_url(entry.source_url)
    markdown, warnings = _parse_content(content, entry.source_url, content_type)
    result.warnings = warnings
    result.char_count = len(markdown)

    parents = _chunk_entry_markdown(entry, markdown)
    result.parent_count = len(parents)

    embed_inputs: list[str] = []
    for parent in parents:
        prepend_scheme = entry.scheme_name or ""
        for child in parent.children:
            embed_inputs.append(
                f"{prepend_scheme} | {child.section_heading}\n{child.text}".strip()
            )

    embeddings = embed_texts(embed_inputs) if embed_inputs else []
    result.child_count = len(embeddings)

    result.status = _classify_status(
        markdown, warnings, result.child_count, structured_tabular=entry.structured_tabular
    )

    if result.status == ParseStatus.FAILED:
        result.error = "No extractable text or zero chunks"
        logger.warning("Skipped %s: %s", entry.source_name, result.error)
        return result

    document_id = insert_document(conn, entry, markdown)
    insert_chunks(conn, document_id, entry, parents, embeddings)
    conn.commit()
    logger.info(
        "Ingested %s: %s (%d parents, %d children)",
        result.status.value,
        entry.source_name,
        result.parent_count,
        result.child_count,
    )
    return result


def _result_from_db(conn, entry: SourceEntry) -> DocumentResult | None:
    stats = get_document_stats(conn, entry.source_url)
    if stats is None:
        return None
    char_count, parent_count, child_count = stats
    markdown = get_parsed_text(conn, entry.source_url) or ""
    status = _classify_status(
        markdown, [], child_count, structured_tabular=entry.structured_tabular
    )
    return DocumentResult(
        entry=entry,
        status=status,
        char_count=char_count,
        parent_count=parent_count,
        child_count=child_count,
    )


def run_ingestion(
    source_list_path,
    *,
    clear_corpus_first: bool = True,
    only_urls: set[str] | None = None,
) -> list[DocumentResult]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    entries = load_sources_from_markdown(source_list_path)
    if only_urls is not None:
        entries = [e for e in entries if e.source_url in only_urls]
        if not entries:
            raise ValueError("No entries matched only_urls filter")

    apply_migrations()
    if clear_corpus_first:
        clear_corpus()

    run_results: dict[str, DocumentResult] = {}

    with get_connection() as conn:
        for entry in entries:
            result = DocumentResult(entry=entry, status=ParseStatus.FAILED)
            try:
                result = _ingest_single_entry(conn, entry)
            except Exception as exc:  # noqa: BLE001
                result.status = ParseStatus.FAILED
                result.error = str(exc)
                logger.exception("Failed %s", entry.source_name)
                conn.rollback()
            run_results[entry.source_url] = result

        if only_urls is not None:
            all_entries = load_sources_from_markdown(source_list_path)
            merged: list[DocumentResult] = []
            for entry in all_entries:
                if entry.source_url in run_results:
                    merged.append(run_results[entry.source_url])
                else:
                    db_result = _result_from_db(conn, entry)
                    if db_result:
                        merged.append(db_result)
                    else:
                        merged.append(
                            DocumentResult(
                                entry=entry,
                                status=ParseStatus.FAILED,
                                error="Not ingested",
                            )
                        )
            return merged

        all_entries = load_sources_from_markdown(source_list_path)
        return [run_results[e.source_url] for e in all_entries]


def retry_embedding_for_entry(
    conn,
    entry: SourceEntry,
    markdown: str,
    *,
    embed_batch_size: int | None = None,
    embed_batch_pause_seconds: float | None = None,
) -> DocumentResult:
    """Re-chunk and embed from existing parsed markdown (no fetch/parse)."""
    result = DocumentResult(entry=entry, status=ParseStatus.FAILED)
    result.char_count = len(markdown)
    result.warnings = []

    parents = _chunk_entry_markdown(entry, markdown)
    result.parent_count = len(parents)

    embed_inputs: list[str] = []
    for parent in parents:
        prepend_scheme = entry.scheme_name or ""
        for child in parent.children:
            embed_inputs.append(
                f"{prepend_scheme} | {child.section_heading}\n{child.text}".strip()
            )

    embeddings = (
        embed_texts(
            embed_inputs,
            batch_size=embed_batch_size,
            batch_pause_seconds=embed_batch_pause_seconds,
        )
        if embed_inputs
        else []
    )
    result.child_count = len(embeddings)
    result.status = _classify_status(
        markdown, result.warnings, result.child_count, structured_tabular=entry.structured_tabular
    )

    if result.status == ParseStatus.FAILED:
        result.error = "No extractable text or zero chunks after embed"
        return result

    latest_id = get_latest_document_id(conn, entry.source_url)
    if latest_id:
        delete_chunks_for_document(conn, latest_id)
        conn.execute(
            "UPDATE source_documents SET parsed_text = %s WHERE document_id = %s",
            (markdown, latest_id),
        )
        document_id = latest_id
    else:
        document_id = insert_document(conn, entry, markdown)
    insert_chunks(conn, document_id, entry, parents, embeddings)
    conn.commit()
    logger.info(
        "Embed retry %s: %s (%d parents, %d children)",
        result.status.value,
        entry.source_name,
        result.parent_count,
        result.child_count,
    )
    return result


def run_embedding_retry(
    source_list_path,
    urls: set[str],
    *,
    allow_stage_missing: bool = False,
    embed_batch_size: int | None = None,
    embed_batch_pause_seconds: float | None = None,
    url_order: list[str] | None = None,
) -> list[DocumentResult]:
    """Retry embedding using parsed_text already stored in source_documents."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    apply_migrations()
    entries = [e for e in load_sources_from_markdown(source_list_path) if e.source_url in urls]
    if len(entries) != len(urls):
        found = {e.source_url for e in entries}
        missing = urls - found
        raise ValueError(f"URLs not in source list: {sorted(missing)}")

    if url_order:
        order_map = {u: i for i, u in enumerate(url_order)}
        entries.sort(key=lambda e: order_map.get(e.source_url, 999))

    results: list[DocumentResult] = []
    with get_connection() as conn:
        for entry in entries:
            result = DocumentResult(entry=entry, status=ParseStatus.FAILED)
            markdown = get_parsed_text(conn, entry.source_url)
            if not markdown or not markdown.strip():
                if not allow_stage_missing:
                    result.error = "No parsed_text in corpus DB — embed failed before document write"
                    results.append(result)
                    continue
                logger.warning(
                    "Staging parsed_text for %s (missing from DB after embed failure)",
                    entry.source_name,
                )
                content, content_type = fetch_url(entry.source_url)
                markdown, warnings = _parse_content(content, entry.source_url, content_type)
                result.warnings = warnings
            try:
                result = retry_embedding_for_entry(
                    conn,
                    entry,
                    markdown,
                    embed_batch_size=embed_batch_size,
                    embed_batch_pause_seconds=embed_batch_pause_seconds,
                )
                if result.warnings:
                    pass
            except Exception as exc:  # noqa: BLE001
                result.status = ParseStatus.FAILED
                result.error = str(exc)
                logger.exception("Embed retry failed %s", entry.source_name)
                conn.rollback()
            results.append(result)
    return results
