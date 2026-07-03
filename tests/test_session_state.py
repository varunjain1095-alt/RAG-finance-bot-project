"""Session state and context reignition tests."""

import unittest
import uuid

from rag_bot.generation.experience_level import ExperienceLevelCommand
from rag_bot.generation.session_state import (
    ROLLING_TURN_WINDOW,
    SessionState,
    apply_level_command,
    apply_refusal_event,
    apply_scheme_detection,
    append_recent_turn,
    build_conversation_context,
    format_structured_facts,
)


class SessionStateTests(unittest.TestCase):
    def test_scheme_detection_updates_active_scheme(self) -> None:
        state = SessionState()
        apply_scheme_detection(state, "What is Flexicap expense ratio?")
        self.assertEqual(
            state.active_scheme,
            "ICICI Prudential Flexicap Fund",
        )
        self.assertIn("ICICI Prudential Flexicap Fund", state.schemes_discussed)

    def test_follow_up_scheme_context_in_structured_facts(self) -> None:
        state = SessionState()
        apply_scheme_detection(state, "What is Flexicap expense ratio?")
        facts = format_structured_facts(state)
        self.assertIn("Flexicap", facts)
        self.assertIn("Most recently discussed scheme", facts)

    def test_rolling_window_caps_at_five(self) -> None:
        state = SessionState()
        for i in range(7):
            append_recent_turn(
                state,
                turn_id=uuid.uuid4(),
                question=f"Q{i}",
                answer=f"A{i}",
            )
        self.assertEqual(len(state.recent_turns), ROLLING_TURN_WINDOW)
        self.assertEqual(state.recent_turns[0]["question"], "Q2")

    def test_refusal_events_recorded(self) -> None:
        state = SessionState()
        apply_refusal_event(state, "no_performance", "What is the 5-year CAGR?")
        self.assertEqual(len(state.refusal_events), 1)
        self.assertEqual(state.refusal_events[0]["category"], "no_performance")

    def test_level_preference_recorded(self) -> None:
        state = SessionState()
        cmd = ExperienceLevelCommand("expert", "expert_mode")
        apply_level_command(state, cmd)
        self.assertIn("expert_mode", state.preferences)

    def test_load_whole_mode_includes_recent_turns(self) -> None:
        state = SessionState()
        append_recent_turn(
            state,
            turn_id=uuid.uuid4(),
            question="What is ELSS lock-in?",
            answer="ELSS has a 3-year lock-in.",
        )
        context = build_conversation_context(uuid.uuid4(), state, "What about exit load?")
        self.assertIn("Recent conversation", context)
        self.assertIn("ELSS lock-in", context)

    def test_state_roundtrip_json(self) -> None:
        state = SessionState(schemes_discussed=["ICICI Prudential Flexicap Fund"])
        restored = SessionState.from_db(state.to_dict())
        self.assertEqual(restored.schemes_discussed, state.schemes_discussed)


if __name__ == "__main__":
    unittest.main()
