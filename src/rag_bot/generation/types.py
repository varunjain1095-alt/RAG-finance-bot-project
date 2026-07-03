"""Generation pipeline types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


class RefusalCategory(str, Enum):
    PII = "pii"
    OUT_OF_SCOPE = "out_of_scope"
    NO_PERFORMANCE = "no_performance"
    THIN_RETRIEVAL = "thin_retrieval"
    MIXED_FACTUAL_ADVISORY = "mixed_factual_advisory"


class FilterResultKind(str, Enum):
    PASS = "pass"
    PII = "pii"
    OUT_OF_SCOPE = "out_of_scope"
    NO_PERFORMANCE = "no_performance"
    MIXED = "mixed"


@dataclass
class FilterResult:
    kind: FilterResultKind
    pii_type: str | None = None
    detection_method: str = "rule"


@dataclass
class CitationFlow:
    citation_present: bool = False
    cited_url: str | None = None
    url_provenance_passed: bool = False
    required_regeneration: bool = False
    final_outcome: str = "none"
    failure_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "citation_present": self.citation_present,
            "cited_url": self.cited_url,
            "url_provenance_passed": self.url_provenance_passed,
            "required_regeneration": self.required_regeneration,
            "final_outcome": self.final_outcome,
            "failure_mode": self.failure_mode,
        }


@dataclass
class GenerationTimings:
    input_filters_ms: float = 0.0
    embedding_ms: float = 0.0
    retrieval_ms: float = 0.0
    rerank_ms: float = 0.0
    generation_ms: float = 0.0
    postprocessing_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class AskResult:
    turn_id: uuid.UUID
    session_id: uuid.UUID
    answer: str
    refusal_category: str | None = None
    cited_url: str | None = None
    experience_level: str = "somewhat_familiar"
    timings: GenerationTimings = field(default_factory=GenerationTimings)
    cost_usd: float = 0.0
    citation_flow: CitationFlow = field(default_factory=CitationFlow)
    debug: dict[str, Any] = field(default_factory=dict)
