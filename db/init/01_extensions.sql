-- Phase 0: enable pgvector for Phase 1 embeddings (768-dim bge-base-en-v1.5).

CREATE EXTENSION IF NOT EXISTS vector;
