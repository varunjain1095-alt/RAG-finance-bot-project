"""Prompt assembly for Claude generation."""

from pathlib import Path

from rag_bot.config import PROJECT_ROOT

PROMPTS_ROOT = PROJECT_ROOT / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_ROOT / "system_prompt.md"
EXAMPLE_CATEGORIES = ("factual", "out_of_scope", "thin_retrieval", "mixed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_experience_instructions(level: str) -> str:
    path = PROMPTS_ROOT / "experience_levels" / level / "instructions.md"
    if not path.is_file():
        path = PROMPTS_ROOT / "experience_levels" / "somewhat_familiar" / "instructions.md"
    return _read(path)


def load_few_shot_examples(level: str) -> str:
    parts: list[str] = []
    for category in EXAMPLE_CATEGORIES:
        path = PROMPTS_ROOT / "experience_levels" / level / "examples" / f"{category}.md"
        if path.is_file():
            parts.append(f"### Example: {category}\n{_read(path)}")
    return "\n\n".join(parts)


def assemble_prompt(
    *,
    experience_level: str,
    retrieved_sources: str,
    user_question: str,
    conversation_state: str = "",
    serial_section_block: str = "",
) -> str:
    template = _read(SYSTEM_PROMPT_PATH)
    body = (
        template.replace(
            "{{experience_level_instructions}}",
            load_experience_instructions(experience_level),
        )
        .replace("{{few_shot_examples}}", load_few_shot_examples(experience_level))
        .replace(
            "{{conversation_state}}",
            conversation_state or "No prior conversation state.",
        )
        .replace("{{serial_section_block}}", serial_section_block)
        .replace("{{retrieved_sources}}", retrieved_sources)
        .replace("{{user_question}}", user_question)
    )
    return body
