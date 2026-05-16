"""
query_service.py — Application service for query workflows.

Bridges the FastAPI route layer and the Orchestrator.  The service returns
structured Python objects; SSE formatting is the route layer's responsibility.

Fix #6 — this service no longer emits `data: ...\\n\\n` SSE strings.
          It yields plain dicts that the route wraps in SSE framing.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.schemas.query import QueryRequest
from core.orchestrator import Orchestrator
from core.types import GenerationResult, RerankedChunk

__all__ = ["QueryService"]

logger = logging.getLogger(__name__)


class QueryService:
    """Application service for query workflows.

    Args:
        orchestrator: The central RAG pipeline coordinator.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        # Store last reranked chunks so the route can attach sources after streaming.
        self._last_sources: list[RerankedChunk] | None = None

    async def answer(self, request: QueryRequest) -> GenerationResult:
        """Run the full RAG pipeline and return the complete result.

        FIX #4 — returns the full :class:`GenerationResult` (answer +
        sources + latency_ms + confidence) instead of just the answer string,
        so the route can build a complete QueryResponse.

        Args:
            request: Validated query request.

        Returns:
            :class:`GenerationResult` with answer, reranked sources,
            per-stage latency breakdown, and ConfidenceMetrics.
        """
        logger.info("answer: question=%r", request.question)
        result = await self._orchestrator.answer(
            request.question,
            top_k_retrieval=request.top_k_retrieval,
            top_k_rerank=request.top_k_rerank,
            use_hyde=request.use_hyde,
        )
        logger.info(
            "answer complete: sources=%d latency=%s confidence=%s",
            len(result.sources), result.latency_ms, result.confidence,
        )
        return result

    async def stream_answer(self, request: QueryRequest) -> AsyncIterator[dict[str, Any]]:
        """Retrieve context then stream answer tokens as plain dicts.

        FIX #6 — yields structured dicts instead of SSE-formatted strings.
                  The route layer is responsible for `data: ...\\n\\n` framing.

        FIX #5 — source payload now includes score and rank from RerankedChunk.

        FIX: done event now includes ``confidence`` with server-side metrics.

        Yields:
            ``{"type": "token", "token": str}`` — one per token.
            ``{"type": "done", "sources": [...], "latency_ms": {...},
                "confidence": {...}}`` — terminator.

        Args:
            request: Validated query request.
        """
        logger.info("stream_answer: question=%r", request.question)

        # FIX: unpack the new 3-tuple from retrieve_context
        reranked, timings, mean_confidence = await self._orchestrator.retrieve_context(
            request.question,
            top_k_retrieval=request.top_k_retrieval,
            top_k_rerank=request.top_k_rerank,
            use_hyde=request.use_hyde,
        )

        async for token in self._orchestrator.stream_answer(
            request.question,
            [item.chunk for item in reranked],
        ):
            yield {"type": "token", "token": token}

        # Cache sources so get_last_sources() can return them after streaming.
        self._last_sources = list(reranked)

        # FIX: build ConfidenceMetrics and attach to the done payload
        confidence_metrics = self._orchestrator._build_confidence(reranked, mean_confidence)

        yield {
            "type": "done",
            # FIX #5 — full source payload with score + rank
            "sources": [_source_payload(chunk) for chunk in reranked],
            "latency_ms": timings,
            # FIX: confidence payload for route to emit as [CONFIDENCE] event
            "confidence": {
                "answer_confidence": confidence_metrics.answer_confidence,
                "source_coverage": confidence_metrics.source_coverage,
                "sources_used": confidence_metrics.sources_used,
                "retrieved_chunks": confidence_metrics.retrieved_chunks,
            },
        }
        logger.info(
            "stream_answer complete: sources=%d latency=%s confidence=%s",
            len(reranked), timings, confidence_metrics,
        )

    async def get_last_sources(self, request: QueryRequest) -> list[dict[str, Any]]:
        """Return the sources from the most recent stream_answer call.

        FIX #7 — called by the route after streaming completes to attach
        sources to the SSE event stream.  Returns [] if no prior call exists.
        """
        if self._last_sources is None:
            return []
        return [_source_payload(chunk) for chunk in self._last_sources]


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _source_payload(chunk: RerankedChunk) -> dict[str, Any]:
    """Serialise a :class:`RerankedChunk` to a JSON-safe dict.

    FIX #5 — includes ``score`` and ``rank`` which SourceViewer needs for
    citation ordering and confidence display.
    """
    return {
        "chunk_id": chunk.chunk.chunk_id,
        "source_id": chunk.chunk.source_id,
        "score": round(chunk.score, 4),
        "rank": chunk.rank,
        "text_preview": chunk.chunk.text[:200],
        "metadata": dict(chunk.chunk.metadata),
    }
