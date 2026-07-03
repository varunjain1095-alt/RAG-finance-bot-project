"""Retrieval result types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RetrievalOutcome(str, Enum):
    SUCCESS = "success"
    SCOPE_REFUSAL = "scope_refusal"
    CLARIFICATION = "clarification"
    THIN_RETRIEVAL = "thin_retrieval"
    NO_DATA = "no_data"


@dataclass
class ChildCandidate:
    child_chunk_id: str
    parent_chunk_id: str
    text: str
    scheme_name: str | None
    rrf_score: float = 0.0
    rerank_score: float | None = None
    semantic_score: float | None = None


@dataclass
class ParentContext:
    parent_chunk_id: str
    text: str
    source_name: str
    date_version: str
    source_url: str
    scheme_name: str | None
    rerank_score: float | None = None
    formatted_text: str = ""


@dataclass
class TimingMs:
    scheme_detection: float = 0.0
    expansion: float = 0.0
    embed: float = 0.0
    retrieval: float = 0.0
    rerank: float = 0.0
    assembly: float = 0.0
    total: float = 0.0


@dataclass
class RetrievalResult:
    outcome: RetrievalOutcome
    query: str
    parents: list[ParentContext] = field(default_factory=list)
    message: str | None = None
    detected_scheme: str | None = None
    top_rerank_score: float | None = None
    rerank_used: bool = True
    timing: TimingMs = field(default_factory=TimingMs)
    debug: dict[str, Any] = field(default_factory=dict)
