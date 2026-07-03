"""UI config sourced from regulatory templates."""

import unittest

from rag_bot.ui_config import (
    CHAT_FOOTER_DISCLAIMER,
    EXPERIENCE_LEVEL_QUESTION,
    OPENING_GREETING,
    build_ui_config,
)


class UiConfigTests(unittest.TestCase):
    def test_opening_greeting_exact(self) -> None:
        self.assertEqual(
            OPENING_GREETING,
            "Welcome to IND money's intelligence bot, type question to begin",
        )

    def test_experience_question_exact(self) -> None:
        self.assertEqual(
            EXPERIENCE_LEVEL_QUESTION,
            "How familiar are you with financial products and investing?",
        )

    def test_build_ui_config_includes_regulatory_copy(self) -> None:
        cfg = build_ui_config()
        self.assertEqual(cfg["bot_name"], "ICICI PRU FAQ")
        self.assertEqual(cfg["opening_greeting"], OPENING_GREETING)
        self.assertEqual(cfg["disclaimer_line"], CHAT_FOOTER_DISCLAIMER)
        self.assertNotIn("suggested_questions", cfg)


if __name__ == "__main__":
    unittest.main()
