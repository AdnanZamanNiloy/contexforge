"""
schemas/query.py — Request and response schemas for query endpoints.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["ConfidenceMetrics", "QueryRequest", "QueryResponse", "SourceSummary"]


# FIX: new Pydantic model so the frontend receives clean server-side confidence
class ConfidenceMetrics(BaseModel):
    """Server-side confidence and coverage computed by the orchestrator.

    All fields are required — the backend always computes these values.
    ``answer_confidence`` is validated to the [0.0, 1.0] range.
    """

    answer_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Sigmoid-normalised mean cross-encoder score [0.0, 1.0].",
    )
    source_coverage: Literal["Excellent", "Strong", "Moderate", "Low", "Weak"] = Field(
        ...,
        description="Categorical label derived from answer_confidence.",
    )
    sources_used: int = Field(
        ...,
        ge=0,
        description="Number of unique source documents among retrieved chunks.",
    )
    retrieved_chunks: int = Field(
        ...,
        ge=0,
        description="Total chunks returned by the reranker.",
    )

    model_config = {"frozen": True}


class QueryRequest(BaseModel):
    """Request body for POST /query and POST /query/stream.

    Attributes:
        question:        User question.  Must be non-blank after stripping.
        top_k_retrieval: Candidates per retrieval leg.  Defaults to
                         ``settings.TOP_K_RETRIEVAL`` when omitted.
        top_k_rerank:    Final chunks after reranking.  Defaults to
                         ``settings.TOP_K_RERANK`` when omitted.
        use_hyde:        Override the server-side HyDE flag for this request.
    """

    question: str = Field(
        ...,
        min_length=1,
        description="The question to answer.  Must be non-blank.",
        examples=["What is Reciprocal Rank Fusion?"],
    )
    # FIX #2 — upper bounds prevent absurd values reaching FAISS / BM25
    top_k_retrieval: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Override retrieval candidate count (1–200).",
    )
    top_k_rerank: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Override reranked result count (1–20).",
    )
    use_hyde: bool | None = Field(
        default=None,
        description="Override server-side HyDE flag for this request.",
    )

    # FIX #3 — reject whitespace-only questions that pass min_length=1
    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank or whitespace-only")
        return v.strip()

    model_config = {"frozen": True}


class SourceSummary(BaseModel):
    """A single cited source chunk returned with a query response.

    FIX #1 — exposes the fields SourceViewer needs for citation display.
    """

    chunk_id: str
    source_id: str | None
    score: float = Field(description="Cross-encoder rerank score.")
    rank: int = Field(description="1-based rank after reranking.")
    text_preview: str = Field(description="First 200 characters of the chunk.")
    metadata: dict = Field(default_factory=dict)


class QueryResponse(BaseModel):
    """Response body for POST /query.

    FIX #1 — includes ``sources`` and ``latency_ms`` so the frontend
    SourceViewer can render citations and the client can observe pipeline
    performance without needing Langfuse access.

    FIX: now includes ``confidence`` with server-side ConfidenceMetrics.
    """

    answer: str = Field(description="Generated answer grounded in retrieved sources.")
    sources: list[SourceSummary] = Field(
        default_factory=list,
        description="Reranked source chunks used as context, with scores and ranks.",
    )
    latency_ms: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-stage latency breakdown. "
            "Keys: hyde_ms, embed_ms, retrieve_ms, rerank_ms."
        ),
    )
    # FIX: attach server-side ConfidenceMetrics — the frontend should not re-derive
    confidence: ConfidenceMetrics | None = Field(
        default=None,
        description="Server-side confidence and coverage metrics.",
    )

    model_config = {"frozen": True}
