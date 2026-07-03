"""Apply DB migrations."""

import logging

from rag_bot.ingestion.db import apply_migrations

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
applied = apply_migrations()
print(f"migrations ok ({len(applied)} newly applied: {', '.join(applied) if applied else 'none'})")
