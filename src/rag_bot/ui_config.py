"""UI copy and config sourced from regulatory templates and locked prompts."""

from rag_bot.operations.regulatory import (
    amfi_investor_url,
    load_ui_disclaimer_snippet,
)

OPENING_GREETING = (
    "Welcome to IND money's intelligence bot, type question to begin"
)

EXPERIENCE_LEVEL_OPTIONS: list[dict[str, str]] = [
    {"level": "new", "label": "New"},
    {"level": "somewhat_familiar", "label": "Somewhat familiar"},
    {"level": "expert", "label": "Expert"},
]

EXPERIENCE_LEVEL_QUESTION = (
    "How familiar are you with financial products and investing?"
)

LEARNINGS_PROMPT = "Download your learnings so you can have a look later on?"

CHAT_FOOTER_DISCLAIMER = (
    "The bot does not provide advice on which specific funds you should purchase."
)


def build_ui_config() -> dict:
    disclaimer_full = load_ui_disclaimer_snippet()
    learn_more_url = amfi_investor_url()
    return {
        "bot_name": "ICICI PRU FAQ",
        "opening_greeting": OPENING_GREETING,
        "input_placeholder": "What would you like to learn?",
        "disclaimer_line": CHAT_FOOTER_DISCLAIMER,
        "disclaimer_detail": disclaimer_full,
        "learn_more_url": learn_more_url,
        "learn_more_label": "Learn more",
        "experience_level_question": EXPERIENCE_LEVEL_QUESTION,
        "experience_level_options": EXPERIENCE_LEVEL_OPTIONS,
        "learnings_prompt": LEARNINGS_PROMPT,
        "themes": [
            {"id": "light", "label": "Light"},
            {"id": "dark-navy", "label": "Dark navy"},
            {"id": "true-black", "label": "True black"},
        ],
    }
