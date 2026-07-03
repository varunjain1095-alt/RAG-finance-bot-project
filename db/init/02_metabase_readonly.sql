-- Read-only role for Metabase (Phase 5). Password overridden in production via secrets manager.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'metabase_readonly') THEN
    CREATE ROLE metabase_readonly WITH LOGIN PASSWORD 'metabase_readonly';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE rag_bot TO metabase_readonly;
GRANT USAGE ON SCHEMA public TO metabase_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO metabase_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO metabase_readonly;
