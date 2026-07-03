"""Structure-aware chunking into parent (600–800 tokens) and child (100–200 tokens) chunks."""

import re
from dataclasses import dataclass

import tiktoken

ENCODER = tiktoken.get_encoding("cl100k_base")

PARENT_MIN = 600
PARENT_MAX = 800
CHILD_MIN = 100
CHILD_MAX = 200
CHILD_OVERLAP = 20  # ~10% of child max


def count_tokens(text: str) -> int:
    return len(ENCODER.encode(text))


@dataclass
class ChunkUnit:
    text: str
    section_heading: str


@dataclass
class ParentChunkData:
    text: str
    section_heading: str
    children: list[ChunkUnit]
    citation_url: str | None = None
    scheme_name: str | None = None


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    if not markdown.strip():
        return [("Document", "")]

    parts = re.split(r"(?=^#{1,6}\s+)", markdown, flags=re.MULTILINE)
    sections: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", part, flags=re.MULTILINE)
        if heading_match:
            heading = heading_match.group(2).strip()
            body = re.sub(r"^#{1,6}\s+.+$", "", part, count=1, flags=re.MULTILINE).strip()
        else:
            heading = "Document"
            body = part
        sections.append((heading, body))
    return sections or [("Document", markdown)]


def _recursive_split(text: str, max_tokens: int) -> list[str]:
    tokens = count_tokens(text)
    if tokens <= max_tokens:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) > 1:
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for para in paragraphs:
            para_tokens = count_tokens(para)
            if current_tokens + para_tokens > max_tokens and current:
                chunks.append("\n\n".join(current))
                current = [para]
                current_tokens = para_tokens
            else:
                current.append(para)
                current_tokens += para_tokens
        if current:
            chunks.append("\n\n".join(current))
        return chunks

    # Character-level fallback
    words = text.split()
    chunks: list[str] = []
    current_words: list[str] = []
    for word in words:
        current_words.append(word)
        if count_tokens(" ".join(current_words)) > max_tokens:
            chunks.append(" ".join(current_words))
            current_words = []
    if current_words:
        chunks.append(" ".join(current_words))
    return chunks


def _build_parent_sections(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    parents: list[tuple[str, str]] = []
    buffer_heading = ""
    buffer_text: list[str] = []
    buffer_tokens = 0

    for heading, body in sections:
        block = f"{heading}\n\n{body}".strip()
        block_tokens = count_tokens(block)
        if block_tokens > PARENT_MAX:
            if buffer_text:
                parents.append((buffer_heading or heading, "\n\n".join(buffer_text)))
                buffer_text, buffer_tokens, buffer_heading = [], 0, ""
            for piece in _recursive_split(block, PARENT_MAX):
                parents.append((heading, piece))
            continue

        if buffer_tokens + block_tokens > PARENT_MAX and buffer_text:
            parents.append((buffer_heading, "\n\n".join(buffer_text)))
            buffer_text, buffer_tokens = [block], block_tokens
            buffer_heading = heading
        else:
            if not buffer_heading:
                buffer_heading = heading
            buffer_text.append(block)
            buffer_tokens += block_tokens

    if buffer_text:
        parents.append((buffer_heading or "Document", "\n\n".join(buffer_text)))
    return parents


def _split_children(parent_text: str, section_heading: str) -> list[ChunkUnit]:
    if count_tokens(parent_text) <= CHILD_MAX:
        return [ChunkUnit(text=parent_text, section_heading=section_heading)]

    children: list[ChunkUnit] = []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", parent_text) if p.strip()]
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if para_tokens > CHILD_MAX:
            for piece in _recursive_split(para, CHILD_MAX):
                children.append(ChunkUnit(text=piece, section_heading=section_heading))
            continue

        if current_tokens + para_tokens > CHILD_MAX and current:
            children.append(
                ChunkUnit(text="\n\n".join(current), section_heading=section_heading)
            )
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        children.append(ChunkUnit(text="\n\n".join(current), section_heading=section_heading))

    return children


def chunk_markdown(markdown: str) -> list[ParentChunkData]:
    sections = _split_sections(markdown)
    parent_sections = _build_parent_sections(sections)
    results: list[ParentChunkData] = []

    for heading, parent_text in parent_sections:
        parent_text = parent_text.strip()
        if not parent_text:
            continue
        children = _split_children(parent_text, heading)
        if not children:
            children = [ChunkUnit(text=parent_text, section_heading=heading)]
        results.append(
            ParentChunkData(text=parent_text, section_heading=heading, children=children)
        )

    if not results and markdown.strip():
        results.append(
            ParentChunkData(
                text=markdown.strip(),
                section_heading="Document",
                children=[ChunkUnit(text=markdown.strip(), section_heading="Document")],
            )
        )
    return results
