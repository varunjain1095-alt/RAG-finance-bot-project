-- Version history per source_url: multiple rows allowed; is_latest marks current per URL.

ALTER TABLE source_documents
    DROP CONSTRAINT IF EXISTS source_documents_source_url_key;

CREATE INDEX IF NOT EXISTS idx_source_documents_source_url
    ON source_documents (source_url);

CREATE INDEX IF NOT EXISTS idx_source_documents_latest
    ON source_documents (source_url)
    WHERE is_latest = TRUE;
