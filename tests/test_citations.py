"""Citation enforcement tests."""

import unittest

from rag_bot.generation.citations import (
    apply_citation_hierarchy,
    enforce_citation,
    is_broad_conceptual_question,
    is_runaway_body,
    parse_citation_block,
    pick_citation_parent,
    runaway_limits,
)
from rag_bot.operations.regulatory import icici_pru_ter_disclosure_url
from rag_bot.retrieval.types import ParentContext


class CitationEnforcementTests(unittest.TestCase):
    def _parent(
        self,
        url: str,
        name: str = "TER Source",
        date: str = "2026-06",
    ) -> ParentContext:
        return ParentContext(
            parent_chunk_id="p1",
            text="TER is 1.2%",
            source_name=name,
            date_version=date,
            source_url=url,
            scheme_name="ICICI Prudential Flexicap Fund",
            formatted_text="",
        )

    def test_valid_citation(self) -> None:
        raw = (
            "[FACTUAL] The expense ratio is 1.2%.\n\n"
            "Last updated from sources: 2026-06\n"
            "Source: [TER Source, 2026-06](corpus:ter-jun2026-flexicap)"
        )
        answer, flow, _ = enforce_citation(
            raw,
            [self._parent("corpus:ter-jun2026-flexicap")],
        )
        self.assertIn("Source:", answer)
        self.assertTrue(flow.url_provenance_passed)
        self.assertEqual(flow.final_outcome, "cited")

    def test_ter_citation_uses_disclosure_not_combined_factsheet(self) -> None:
        query = (
            "What is the difference between the Regular Plan and Direct Plan "
            "expense ratio for ICICI Prudential Balanced Advantage Fund?"
        )
        raw = (
            "[FACTUAL] Regular Plan TER is 1.65%; Direct Plan TER is 0.89%.\n\n"
            "Last updated from sources: 2026-06\n"
            "Source: [ICICI Pru — TER Jun 2026 — Balanced Advantage, 2026-06]"
            "(corpus:ter-jun2026-balanced-advantage)"
        )
        combined_pdf = (
            "https://digitalfactsheet.icicipruamc.com/fact/pdf/"
            "fund-factsheet-for-march-2026.pdf"
        )
        per_scheme = (
            "https://digitalfactsheet.icicipruamc.com/fact/"
            "icici-prudential-balanced-advantage-fund.php"
        )
        ter_disclosure = icici_pru_ter_disclosure_url()
        parents = [
            self._parent(
                "corpus:ter-jun2026-balanced-advantage",
                "ICICI Pru — TER Jun 2026 — Balanced Advantage",
            ),
            self._parent(
                combined_pdf,
                "AMC combined monthly factsheet PDF (Mar 2026)",
                "2026-03",
            ),
            self._parent(per_scheme, "Digital factsheet", "2026-03"),
        ]
        answer, flow, _ = enforce_citation(raw, parents, user_question=query)
        self.assertTrue(flow.url_provenance_passed)
        self.assertEqual(flow.cited_url, ter_disclosure)
        self.assertIn(ter_disclosure, answer)
        self.assertNotIn("fund-factsheet-for-march-2026.pdf", answer)

    def test_ter_hierarchy_maps_corpus_url_to_disclosure(self) -> None:
        ter_disclosure = icici_pru_ter_disclosure_url()
        parents = [
            self._parent("corpus:ter-jun2026-flexicap"),
            self._parent(
                "https://digitalfactsheet.icicipruamc.com/fact/"
                "icici-prudential-flexicap-fund.php",
                "Factsheet",
                "2026-03",
            ),
        ]
        mapped = apply_citation_hierarchy(
            "corpus:ter-jun2026-flexicap",
            parents,
            "What is the expense ratio of Flexicap?",
        )
        self.assertEqual(mapped, ter_disclosure)

    def test_pick_citation_parent_prefers_ter_for_expense_ratio(self) -> None:
        combined_pdf = (
            "https://digitalfactsheet.icicipruamc.com/fact/pdf/"
            "fund-factsheet-for-march-2026.pdf"
        )
        parents = [
            self._parent("corpus:ter-jun2026-flexicap"),
            self._parent(combined_pdf, "Combined factsheet", "2026-03"),
        ]
        picked = pick_citation_parent(
            parents, "What is the expense ratio of ICICI Prudential Flexicap Fund?"
        )
        self.assertEqual(picked.source_url, "corpus:ter-jun2026-flexicap")

    def test_pick_citation_parent_prefers_per_scheme_factsheet_for_nav(self) -> None:
        factsheet_url = (
            "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-flexicap-fund.php"
        )
        combined_pdf = (
            "https://digitalfactsheet.icicipruamc.com/fact/pdf/"
            "fund-factsheet-for-march-2026.pdf"
        )
        parents = [
            self._parent(combined_pdf, "Combined factsheet", "2026-03"),
            self._parent(factsheet_url, "Factsheet", "2026-03"),
        ]
        picked = pick_citation_parent(parents, "What is the NAV of Flexicap?")
        self.assertEqual(picked.source_url, factsheet_url)

    def test_fallback_sets_cited_url(self) -> None:
        raw = "[FACTUAL] Some answer without citation block."
        answer, flow, _ = enforce_citation(
            raw,
            [self._parent("corpus:ter-jun2026-flexicap")],
            user_question="What is exit load for ELSS?",
            top_rerank_score=0.85,
            grounding_threshold=0.35,
        )
        self.assertEqual(flow.final_outcome, "fallback_refusal")
        self.assertEqual(flow.cited_url, "corpus:ter-jun2026-flexicap")
        self.assertIn("corpus:ter-jun2026-flexicap", answer)

    def test_parse_citation(self) -> None:
        parsed = parse_citation_block(
            "Body text.\nLast updated from sources: 2026-06\n"
            "Source: [Name, 2026-06](http://example.com/doc)"
        )
        self.assertEqual(parsed.citation_url, "http://example.com/doc")
        self.assertEqual(parsed.body, "Body text.")


class RunawayLengthTests(unittest.TestCase):
    EXPLAIN_MF_BODY = (
        "A mutual fund is a collective investment vehicle where money from many "
        "investors is pooled together and professionally managed to invest in "
        "equities, bonds, government securities, and money market instruments. "
        "Here's how it works:\n\n"
        "**The basics:** A fund manager invests this pooled money according to "
        "the scheme's objective. Any income or gains generated are distributed "
        "proportionately to investors (after deducting fees and expenses) based "
        "on their unit holdings. In return, the mutual fund charges a small "
        "annual fee to cover management costs.\n\n"
        "**Key advantages:**\n"
        "- Access to a diversified portfolio of securities at relatively low cost\n"
        "- Professional management — you don't have to pick individual stocks "
        "or bonds yourself\n"
        "- Flexibility to choose funds matching your goals (education, retirement, "
        "home purchase, etc.)\n"
        "- Participation in capital markets through a regulated, transparent structure\n\n"
        "**Two main types:**\n"
        "- **Equity Funds** invest primarily in stocks — higher risk, but potentially "
        "higher long-term returns; suitable for investors with longer time horizons "
        "(5+ years)\n"
        "- **Debt Funds** invest in fixed-income securities like bonds — lower risk, "
        "more predictable returns; suited for shorter horizons and income seekers\n\n"
        "**Important to know:** Mutual funds are not guaranteed deposits. Returns "
        "depend on underlying market performance and can fluctuate. SEBI regulates "
        "all fees and expenses. It's wise to allow 18–24 months for actively-managed "
        "equity schemes to generate meaningful returns."
    )

    def test_explain_mutual_funds_beginner_not_runaway(self) -> None:
        self.assertTrue(is_broad_conceptual_question("explain mutual funds"))
        self.assertFalse(
            is_runaway_body(
                self.EXPLAIN_MF_BODY,
                experience_level="new",
                question="explain mutual funds",
            )
        )

    def test_explain_mutual_funds_still_runaway_at_expert_cap(self) -> None:
        self.assertTrue(
            is_runaway_body(
                self.EXPLAIN_MF_BODY,
                experience_level="expert",
                question="explain mutual funds",
            )
        )

    def test_minimum_sip_lookup_not_broad_conceptual(self) -> None:
        q = "What is the minimum SIP for Bluechip?"
        self.assertFalse(is_broad_conceptual_question(q))
        self.assertEqual(runaway_limits("new", q), (280, 14))

    def test_beginner_broad_conceptual_gets_bonus_limits(self) -> None:
        self.assertEqual(
            runaway_limits("new", "explain mutual funds"),
            (330, 18),
        )


if __name__ == "__main__":
    unittest.main()
