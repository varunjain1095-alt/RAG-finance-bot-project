"""Pull query_logs for Flexicap expense-ratio eval cases from DB (no API calls)."""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRESERVE = ("DATABASE_URL",)
_preserved = {k: os.environ[k] for k in _PRESERVE if os.environ.get(k)}
load_dotenv(PROJECT_ROOT / ".env", override=True)
for k, v in _preserved.items():
    os.environ[k] = v

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rag_bot.config import reload_settings
from rag_bot.ingestion.db import get_connection

QUERIES = [
    "What is the expense ratio of ICICI Prudential Flexicap Fund?",
    "What is Flexicap expense ratio and should I invest?",
]


def main() -> int:
    reload_settings()
    out_path = PROJECT_ROOT / "evals" / "results" / "flexicap_query_log_compare.json"
    rows_out: list[dict] = []

    with get_connection() as conn:
        for q in QUERIES:
            rows = conn.execute(
                """
                SELECT
                    ql.turn_id,
                    ql.created_at,
                    ql.user_question,
                    ql.final_answer,
                    ql.refusal_category,
                    ql.citation_flow,
                    LENGTH(ql.final_prompt) AS final_prompt_len,
                    ql.final_prompt,
                    LENGTH(ql.raw_llm_output) AS raw_len,
                    ql.raw_llm_output
                FROM query_logs ql
                WHERE ql.user_question = %s
                ORDER BY ql.created_at DESC
                LIMIT 10
                """,
                (q,),
            ).fetchall()

            for row in rows:
                citation_flow = row[5]
                if isinstance(citation_flow, str):
                    citation_flow = json.loads(citation_flow)
                rows_out.append(
                    {
                        "user_question": row[2],
                        "created_at": str(row[1]),
                        "turn_id": str(row[0]),
                        "refusal_category": row[4],
                        "citation_flow": citation_flow,
                        "final_answer_preview": (row[3] or "")[:300],
                        "final_prompt_len": row[6],
                        "raw_len": row[8],
                        "final_prompt": row[7],
                        "raw_llm_output": row[9],
                    }
                )

    out_path.write_text(json.dumps(rows_out, indent=2), encoding="utf-8")
    print(f"Found {len(rows_out)} logged turns")
    for item in rows_out:
        cf = item.get("citation_flow") or {}
        print(
            f"\n--- {item['created_at']} | {cf.get('final_outcome')} | "
            f"refusal={item['refusal_category']} | raw_len={item['raw_len']}"
        )
        print(f"Q: {item['user_question']}")
        print(f"Answer preview: {item['final_answer_preview'][:200]}...")
    print(f"\nWritten {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
