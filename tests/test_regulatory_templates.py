"""Regulatory template verbatim verification."""

import unittest

from rag_bot.generation.refusals import no_performance_refusal_message
from rag_bot.operations.regulatory import (
    load_mandatory_disclaimers,
    load_ui_disclaimer_snippet,
    market_risk_disclaimer,
)
from rag_bot.config import PROJECT_ROOT


MARKET_RISK_VERBATIM = (
    "Mutual Fund investments are subject to market risks, "
    "read all scheme related documents carefully."
)


class RegulatoryTemplateTests(unittest.TestCase):
    def test_market_risk_in_mandatory_template(self) -> None:
        self.assertIn(MARKET_RISK_VERBATIM, load_mandatory_disclaimers())

    def test_market_risk_in_ui_snippet(self) -> None:
        self.assertIn(MARKET_RISK_VERBATIM, load_ui_disclaimer_snippet())

    def test_market_risk_in_learnings_disclaimer(self) -> None:
        path = PROJECT_ROOT / "templates" / "learnings_document_disclaimer.md"
        self.assertIn(MARKET_RISK_VERBATIM, path.read_text(encoding="utf-8"))

    def test_market_risk_in_performance_refusal(self) -> None:
        msg = no_performance_refusal_message("What is Bluechip CAGR?")
        self.assertIn(MARKET_RISK_VERBATIM, msg)

    def test_market_risk_helper_matches_template(self) -> None:
        self.assertEqual(market_risk_disclaimer(), MARKET_RISK_VERBATIM)


if __name__ == "__main__":
    unittest.main()
