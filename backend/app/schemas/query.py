"""
schemas/query.py — Request and response schemas for query endpoints.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

__all__ = ["QueryRequest", "QueryResponse", "SourceSummary"]


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

    model_config = {"frozen": True}