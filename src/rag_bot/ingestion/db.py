"""Database helpers for corpus ingestion."""

from pathlib import Path
import uuid

import psycopg
from pgvector.psycopg import register_vector

from rag_bot.config import get_settings


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(get_settings().database_url)
    register_vector(conn)
    return conn


def apply_migrations() -> list[str]:
    """Apply pending SQL migrations once each; returns newly applied filenames."""
    migrations_dir = Path(__file__).resolve().parents[3] / "db" / "migrations"
    newly_applied: list[str] = []

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        _backfill_migration_records(conn)

        for migration in sorted(migrations_dir.glob("*.sql")):
            name = migration.name
            if _migration_applied(conn, name):
                continue
            sql = migration.read_text(encoding="utf-8")
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                (name,),
            )
            newly_applied.append(name)

        conn.commit()

    return newly_applied


def _migration_applied(conn: psycopg.Connection, migration_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE migration_name = %s",
        (migration_name,),
    ).fetchone()
    return row is not None


def _backfill_migration_records(conn: psycopg.Connection) -> None:
    """Mark migrations already reflected in the live schema (pre-tracking installs)."""
    if not _migration_applied(conn, "001_corpus_schema.sql"):
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'source_documents'
            """
        ).fetchone()
        if row:
            conn.execute(
                "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                ("001_corpus_schema.sql",),
            )

    if not _migration_applied(conn, "002_embedding_768.sql"):
        row = conn.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod) AS embedding_type
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND c.relname = 'child_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        ).fetchone()
        if row and row[0] == "vector(768)":
            conn.execute(
                "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                ("002_embedding_768.sql",),
            )


def clear_corpus() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM child_chunks")
        conn.execute("DELETE FROM parent_chunks")
        conn.execute("DELETE FROM source_documents")
        conn.commit()


def delete_chunks_for_document(conn: psycopg.Connection, document_id: uuid.UUID) -> None:
    conn.execute("DELETE FROM child_chunks WHERE document_id = %s", (document_id,))
    conn.execute("DELETE FROM parent_chunks WHERE document_id = %s", (document_id,))


def get_latest_document_id(conn: psycopg.Connection, source_url: str) -> uuid.UUID | None:
    row = conn.execute(
        """
        SELECT document_id FROM source_documents
        WHERE source_url = %s AND is_latest = TRUE
        ORDER BY date_version DESC, ingested_at DESC
        LIMIT 1
        """,
        (source_url,),
    ).fetchone()
    return row[0] if row else None


def delete_chunks_for_url(conn: psycopg.Connection, source_url: str) -> None:
    document_id = get_latest_document_id(conn, source_url)
    if document_id:
        delete_chunks_for_document(conn, document_id)


def get_parsed_text(conn: psycopg.Connection, source_url: str) -> str | None:
    row = conn.execute(
        """
        SELECT parsed_text FROM source_documents
        WHERE source_url = %s AND is_latest = TRUE
        ORDER BY date_version DESC, ingested_at DESC
        LIMIT 1
        """,
        (source_url,),
    ).fetchone()
    return row[0] if row else None


def delete_document_by_url(conn: psycopg.Connection, source_url: str) -> None:
    rows = conn.execute(
        "SELECT document_id FROM source_documents WHERE source_url = %s",
        (source_url,),
    ).fetchall()
    for (document_id,) in rows:
        conn.execute("DELETE FROM child_chunks WHERE document_id = %s", (document_id,))
        conn.execute("DELETE FROM parent_chunks WHERE document_id = %s", (document_id,))
        conn.execute("DELETE FROM source_documents WHERE document_id = %s", (document_id,))


def get_document_stats(conn: psycopg.Connection, source_url: str) -> tuple[int, int, int] | None:
    row = conn.execute(
        """
        SELECT d.document_id, LENGTH(d.parsed_text)
        FROM source_documents d
        WHERE d.source_url = %s AND d.is_latest = TRUE
        ORDER BY d.date_version DESC, d.ingested_at DESC
        LIMIT 1
        """,
        (source_url,),
    ).fetchone()
    if not row:
        return None
    document_id, char_count = row
    parent_count = conn.execute(
        "SELECT COUNT(*) FROM parent_chunks WHERE document_id = %s",
        (document_id,),
    ).fetchone()[0]
    child_count = conn.execute(
        "SELECT COUNT(*) FROM child_chunks WHERE document_id = %s",
        (document_id,),
    ).fetchone()[0]
    return int(char_count), int(parent_count), int(child_count)


def demote_is_latest_for_source_url(
    conn: psycopg.Connection,
    source_url: str,
) -> None:
    """Demote prior rows for this exact source_url (version replacements of the same document)."""
    conn.execute(
        """
        UPDATE source_documents
        SET is_latest = FALSE
        WHERE source_url = %s
        """,
        (source_url,),
    )


def reconcile_is_latest_flags(conn: psycopg.Connection) -> int:
    """
    Each source_url is an independent document. Mark the newest row per URL as latest.
    Distinct URLs never compete (e.g. two AMFI pages both stay is_latest=true).
    """
    conn.execute("UPDATE source_documents SET is_latest = FALSE")
    conn.execute(
        """
        UPDATE source_documents d
        SET is_latest = TRUE
        FROM (
            SELECT DISTINCT ON (source_url) document_id
            FROM source_documents
            ORDER BY source_url, date_version DESC, ingested_at DESC
        ) winners
        WHERE d.document_id = winners.document_id
        """
    )
    row = conn.execute(
        "SELECT COUNT(*) FROM source_documents WHERE is_latest = TRUE"
    ).fetchone()
    return int(row[0])


def insert_document(
    conn: psycopg.Connection,
    entry,
    parsed_text: str,
) -> uuid.UUID:
    demote_is_latest_for_source_url(conn, entry.source_url)
    document_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO source_documents (
            document_id, source_name, source_type, source_url, date_version,
            is_latest, scheme_name, authority_level, parsed_text
        ) VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s, %s)
        """,
        (
            document_id,
            entry.source_name,
            entry.source_type,
            entry.source_url,
            entry.date_version,
            entry.scheme_name,
            entry.authority_level,
            parsed_text,
        ),
    )
    return document_id


def insert_chunks(
    conn: psycopg.Connection,
    document_id: uuid.UUID,
    entry,
    parents: list,
    embeddings: list[list[float]],
) -> int:
    child_count = 0
    embed_idx = 0
    for parent in parents:
        parent_id = uuid.uuid4()
        metadata = {
            "section_heading": parent.section_heading,
            "source_url": parent.citation_url or entry.source_url,
            "date_version": entry.date_version,
            "source_name": entry.source_name,
        }
        conn.execute(
            """
            INSERT INTO parent_chunks (
                parent_chunk_id, document_id, text, scheme_name, source_type,
                authority_level, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                parent_id,
                document_id,
                parent.text,
                parent.scheme_name or entry.scheme_name,
                entry.source_type,
                entry.authority_level,
                psycopg.types.json.Json(metadata),
            ),
        )

        for child in parent.children:
            prepend_scheme = parent.scheme_name or entry.scheme_name or ""
            embed_text = f"{prepend_scheme} | {child.section_heading}\n{child.text}".strip()
            child_meta = {
                "section_heading": child.section_heading,
                "source_url": parent.citation_url or entry.source_url,
                "date_version": entry.date_version,
                "source_name": entry.source_name,
            }
            embedding = embeddings[embed_idx]
            embed_idx += 1
            conn.execute(
                """
                INSERT INTO child_chunks (
                    child_chunk_id, parent_chunk_id, document_id, text, embedding,
                    scheme_name, source_type, authority_level, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    uuid.uuid4(),
                    parent_id,
                    document_id,
                    embed_text,
                    embedding,
                    parent.scheme_name or entry.scheme_name,
                    entry.source_type,
                    entry.authority_level,
                    psycopg.types.json.Json(child_meta),
                ),
            )
            child_count += 1
    return child_count
