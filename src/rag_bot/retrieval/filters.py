"""Pre-retrieval SQL fragments (Phase 2)."""


def latest_source_document_join(child_alias: str = "c", doc_alias: str = "d") -> str:
    """
    Join child_chunks to the current ingested version of each source document.

    is_latest is per source_url — distinct URLs never compete (e.g. two AMFI pages).
    Scheme-level queries may match multiple latest documents (digital factsheet + TER).
    """
    return (
        f"INNER JOIN source_documents {doc_alias} "
        f"ON {doc_alias}.document_id = {child_alias}.document_id "
        f"AND {doc_alias}.is_latest = TRUE"
    )
