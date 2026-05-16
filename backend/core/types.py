from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

__all__ = [
    "Document",
    "Chunk",
    "RetrievedChunk",
    "RerankedChunk",
    "ConfidenceMetrics",
    "GenerationResult",
]


def _freeze_metadata(metadata: dict[str, Any]) -> MappingProxyType[str, Any]:
    return MappingProxyType(metadata)



@dataclass(frozen=True)
class Document:

    document_id: str
    text: str
    metadata: MappingProxyType[str, Any] = field(default_factory=dict)
    source_type: str | None = None  

    def __post_init__(self) -> None:
       
        if not self.document_id or not self.document_id.strip():
            raise ValueError("Document.document_id must be a non-blank string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(
                f"Document '{self.document_id}': text must be a non-blank string"
            )
      
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class Chunk:

    chunk_id: str
    text: str
    metadata: MappingProxyType[str, Any] = field(default_factory=dict)
    source_id: str | None = None

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.chunk_id.strip():
            raise ValueError("Chunk.chunk_id must be a non-blank string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(
                f"Chunk '{self.chunk_id}': text must be a non-blank string"
            )
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class RetrievedChunk:

    chunk: Chunk
    score: float

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, Chunk):
            raise TypeError(
                f"RetrievedChunk.chunk must be a Chunk, got {type(self.chunk).__name__}"
            )


@dataclass(frozen=True)
class RerankedChunk:

    chunk: Chunk
    score: float
    rank: int

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, Chunk):
            raise TypeError(
                f"RerankedChunk.chunk must be a Chunk, got {type(self.chunk).__name__}"
            )
      
        if self.rank < 1:
            raise ValueError(
                f"RerankedChunk.rank must be >= 1, got {self.rank}"
            )


# FIX: new dataclass carrying all four confidence fields computed server-side
@dataclass(frozen=True)
class ConfidenceMetrics:
    """Normalised confidence and coverage computed by the reranker / orchestrator.

    Fields:
        answer_confidence: Sigmoid-normalised mean of cross-encoder scores [0.0, 1.0].
        source_coverage:   Categorical label derived from answer_confidence.
        sources_used:      Count of unique source documents among the reranked chunks.
        retrieved_chunks:  Total reranked chunks returned (top_k).
    """

    answer_confidence: float
    source_coverage: str
    sources_used: int
    retrieved_chunks: int


@dataclass(frozen=True)
class GenerationResult:

    answer: str
    sources: tuple[RerankedChunk, ...]
    latency_ms: MappingProxyType[str, float] = field(default_factory=dict)
    # FIX: attach server-side ConfidenceMetrics so the frontend never re-derives
    confidence: ConfidenceMetrics | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str) or not self.answer.strip():
            raise ValueError("GenerationResult.answer must be a non-blank string")
       
        if isinstance(self.sources, list):
            object.__setattr__(self, "sources", tuple(self.sources))
        if isinstance(self.latency_ms, dict):
            object.__setattr__(self, "latency_ms", _freeze_metadata(self.latency_ms))
