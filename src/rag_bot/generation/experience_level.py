"""Mid-session experience level command detection."""

import re
from dataclasses import dataclass

from rag_bot.generation.serial_explanations import detect_serial_topic

_LEVEL_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.I), level)
    for pattern, level in [
        (
            r"\b(?:explain\s+simpler|simpler\s+explanations?|beginner\s+mode|"
            r"switch\s+to\s+(?:beginner|new)(?:\s+mode)?|use\s+plain\s+language)\b",
            "new",
        ),
        (
            r"\b(?:more\s+technical|expert\s+mode|switch\s+to\s+expert(?:\s+mode)?|"
            r"be\s+more\s+concise|technical\s+mode)\b",
            "expert",
        ),
        (
            r"\b(?:standard\s+mode|somewhat\s+familiar|switch\s+to\s+(?:standard|normal)"
            r"(?:\s+mode)?|default\s+mode)\b",
            "somewhat_familiar",
        ),
    ]
)

_LEVEL_ACK: dict[str, str] = {
    "new": (
        "Got it — I'll use simpler explanations and plain language from your next message."
    ),
    "somewhat_familiar": (
        "Got it — switching to standard explanations from your next message."
    ),
    "expert": (
        "Got it — switching to expert mode with direct, concise answers from your next message."
    ),
}

_PREFERENCE_BY_LEVEL: dict[str, str] = {
    "new": "explain_simpler",
    "somewhat_familiar": "standard_explanations",
    "expert": "expert_mode",
}


@dataclass(frozen=True)
class ExperienceLevelCommand:
    target_level: str
    preference: str


def detect_experience_level_command(text: str) -> ExperienceLevelCommand | None:
    for pattern, level in _LEVEL_COMMAND_PATTERNS:
        if pattern.search(text):
            return ExperienceLevelCommand(
                target_level=level,
                preference=_PREFERENCE_BY_LEVEL[level],
            )
    return None


def level_acknowledgment(level: str) -> str:
    return _LEVEL_ACK.get(level, _LEVEL_ACK["somewhat_familiar"])


def should_prompt_experience_level(question: str) -> bool:
    """Prompt only for serial explainer topics where answer depth varies by level."""
    return detect_serial_topic(question) is not None
