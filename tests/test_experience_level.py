"""Experience level command detection tests."""

import unittest

from rag_bot.generation.experience_level import (
    detect_experience_level_command,
    level_acknowledgment,
    should_prompt_experience_level,
)


class ExperienceLevelCommandTests(unittest.TestCase):
    def test_explain_simpler_maps_to_new(self) -> None:
        cmd = detect_experience_level_command("Please explain simpler from now on")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.target_level, "new")

    def test_expert_mode_maps_to_expert(self) -> None:
        cmd = detect_experience_level_command("switch to expert mode")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.target_level, "expert")

    def test_standard_mode_maps_to_somewhat_familiar(self) -> None:
        cmd = detect_experience_level_command("switch to standard mode")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.target_level, "somewhat_familiar")

    def test_factual_question_not_a_command(self) -> None:
        self.assertIsNone(
            detect_experience_level_command("What is the expense ratio of Flexicap?")
        )

    def test_acknowledgment_for_each_level(self) -> None:
        for level in ("new", "somewhat_familiar", "expert"):
            self.assertIn("Got it", level_acknowledgment(level))


class ExperiencePromptGateTests(unittest.TestCase):
    TER_QUERY = (
        "What is the difference between the Regular Plan and Direct Plan "
        "expense ratio for ICICI Prudential Balanced Advantage Fund?"
    )

    def test_factual_ter_lookup_does_not_prompt(self) -> None:
        self.assertFalse(should_prompt_experience_level(self.TER_QUERY))

    def test_factual_exit_load_does_not_prompt(self) -> None:
        self.assertFalse(
            should_prompt_experience_level("What is exit load on Flexicap?")
        )

    def test_factual_minimum_sip_does_not_prompt(self) -> None:
        self.assertFalse(
            should_prompt_experience_level(
                "What is the minimum SIP for Bluechip?"
            )
        )

    def test_serial_mutual_funds_prompts(self) -> None:
        self.assertTrue(should_prompt_experience_level("explain mutual funds"))

    def test_serial_sip_prompts(self) -> None:
        self.assertTrue(should_prompt_experience_level("what is SIP?"))


if __name__ == "__main__":
    unittest.main()
