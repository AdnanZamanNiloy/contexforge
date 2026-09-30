"""
query_service.py — Application service for query workflows.

Bridges the FastAPI route layer and the Orchestrator.  The service returns
structured Python objects; SSE formatting is the route layer's responsibility.

Fix #6 — this service no longer emits `data: ...\\n\\n` SSE strings.
          It yields plain dicts that the route wraps in SSE framing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.context.estimator import resolve_context_depth
from app.schemas.query import QueryRequest
from core.generation.grounding import check_grounding
from core.orchestrator import Orchestrator, _is_structure_question
from core.types import GenerationResult, RerankedChunk

__all__ = ["QueryService"]

logger = logging.getLogger(__name__)


def _limits_for(request: QueryRequest) -> dict[str, int]:
    """Resolve the retrieval limits for a request.

    An explicit ``top_k_retrieval`` / ``top_k_rerank`` still wins: those are the
    precise knobs, and a client that sets them knows what it wants.  Otherwise
    ``context_depth`` is the coarse control, and it is applied as asked.

    It used to be clamped down when few sources were selected, so that "broad"
    over two sources reported as the narrower depth.  That clamp made the depth
    control inert for a single source — the one case where the user most wants
    to widen it, because the caps exist to stop sources crowding each other out
    and crowding is impossible when there is only one.  Every depth differs in
    chunk limits as well as source count, so honouring the request always reads
    strictly more, and the caps are hard limits that cannot overflow the prompt.
    """
    if request.top_k_retrieval is not None or request.top_k_rerank is not None:
        return {}
    return resolve_context_depth(request.context_depth)


class QueryService:
    """Application service for query workflows.

    Args:
        orchestrator: The central RAG pipeline coordinator.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator
        # Store last reranked chunks so the route can attach sources after streaming.
        self._last_sources: list[RerankedChunk] | None = None

    async def _manifest_for(self, request: QueryRequest) -> list[str] | None:
        """Indexed file paths, for questions about the project's layout.

        Retrieval ranks chunks, so a structure question can otherwise only be
        answered from the handful that happened to rank — which produced trees
        missing directories the repository plainly has. The index already knows
        every path it holds, so hand that over instead.

        Scoped to the request's selected sources, so a workspace holding several
        repositories never lists them as one project.
        """
        if request.no_sources or not _is_structure_question(request.question):
            return None
        source_ids = set(request.source_ids or [])
        if request.source_id:
            source_ids.add(request.source_id)
        if not source_ids:
            return None
        manifest = await self._orchestrator.file_manifest(source_ids=source_ids)
        if manifest:
            logger.info("structure question: attaching %d indexed file paths", len(manifest))
        return manifest or None

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
        logger.info(
            "answer: question=%r source_id=%s source_ids=%s",
            request.question,
            request.source_id,
            request.source_ids,
        )
        limits = _limits_for(request)
        if request.context_depth and not limits:
            logger.info("answer: explicit top_k overrides context_depth=%s", request.context_depth)

        result = await self._orchestrator.answer(
            request.question,
            top_k_retrieval=request.top_k_retrieval or limits.get("top_k_retrieval"),
            top_k_rerank=request.top_k_rerank or limits.get("top_k_rerank"),
            use_hyde=request.use_hyde,
            source_id=request.source_id,
            source_ids=request.source_ids,
            file_manifest=await self._manifest_for(request),
            use_knowledge_base=not request.no_sources,
            per_source_cap=limits.get("per_source_cap"),
        )
        logger.info(
            "answer complete: sources=%d latency=%s confidence=%s",
            len(result.sources),
            result.latency_ms,
            result.confidence,
        )
        return result

    async def stream_answer(self, request: QueryRequest) -> AsyncIterator[dict[str, Any]]:
        """Retrieve context then stream answer tokens as plain dicts.

        FIX #6 — yields structured dicts instead of SSE-formatted strings.
                  The route layer is responsible for `data: ...\\n\\n` framing.

        FIX #5 — source payload now includes score and rank from RerankedChunk.

        FIX: done event now includes ``confidence`` with server-side metrics.

        Yields:
            ``{"type": "status", "stage": str}`` — emitted as soon as the
                request is accepted, and again once the sources are known, so a
                client has something to show before the first token exists.
                Retrieval and reranking complete in milliseconds; generation is
                what takes seconds, and without these the stream is silent for
                the whole of it.
            ``{"type": "sources", "sources": [...]}`` — emitted once the
                context is chosen, before generation begins.
            ``{"type": "token", "token": str}`` — one per token.
            ``{"type": "done", "sources": [...], "latency_ms": {...},
                "confidence": {...}}`` — terminator.

        Args:
            request: Validated query request.
        """
        logger.info(
            "stream_answer: question=%r source_id=%s source_ids=%s",
            request.question,
            request.source_id,
            request.source_ids,
        )

        # Resolved before generation so a structure question is answered from
        # the whole index rather than from the retrieved chunks alone.
        manifest = await self._manifest_for(request)

        # Sent before any work starts, so the UI can leave its spinner for
        # "searching your sources" immediately rather than sitting on a void.
        yield {"type": "status", "stage": "retrieving"}

        # Unpack the new 3-tuple from retrieve_context
        limits = _limits_for(request)
        reranked, timings, mean_confidence = await self._orchestrator.retrieve_context(
            request.question,
            top_k_retrieval=request.top_k_retrieval or limits.get("top_k_retrieval"),
            top_k_rerank=request.top_k_rerank or limits.get("top_k_rerank"),
            use_hyde=request.use_hyde,
            source_id=request.source_id,
            source_ids=request.source_ids,
            use_knowledge_base=not request.no_sources,
            per_source_cap=limits.get("per_source_cap"),
        )

        # The sources are known now and generation has not started, so this is
        # the one moment the answer is not yet in the way. Sending them here
        # lets the client show what is being read while the model is still
        # thinking, instead of revealing the citations at the very end.
        yield {
            "type": "sources",
            "sources": [_source_payload(chunk) for chunk in reranked],
        }
        yield {"type": "status", "stage": "generating"}

        # Time the LLM stream so generation latency is visible in the
        # breakdown (time-to-first-token + total generation time).
        gen_start = time.perf_counter()
        first_token_ms: float | None = None
        # The full answer is needed after the fact to check it against the
        # retrieved text. Streaming means the text is only complete at the end,
        # so it is accumulated here rather than re-queried later.
        answer_parts: list[str] = []
        try:
            async for token in self._orchestrator.stream_answer(
                request.question,
                [item.chunk for item in reranked],
                file_manifest=manifest,
            ):
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - gen_start) * 1000
                answer_parts.append(token)
                yield {"type": "token", "token": token}
        finally:
            timings["generate_ms"] = (time.perf_counter() - gen_start) * 1000
            if first_token_ms is not None:
                timings["first_token_ms"] = first_token_ms

        # Cache sources so get_last_sources() can return them after streaming.
        self._last_sources = list(reranked)

        # Confidence here must match the non-streaming path exactly. Streaming
        # previously skipped the grounding check, so the UI reported a higher
        # score than the same question returned over POST /query and an
        # invented figure was never penalised. The answer is complete at this
        # point, so the check runs on the accumulated text.
        answer_text = "".join(answer_parts)
        grounding = check_grounding(answer_text, [item.chunk.text for item in reranked]) if reranked else None
        reported = self._orchestrator._build_confidence(reranked, mean_confidence)
        adjusted = self._orchestrator._grounded_confidence(
            reported.answer_confidence,
            answer_text,
            reranked,
            report=grounding,
        )
        confidence_metrics = self._orchestrator._build_confidence(reranked, adjusted)
        reason = self._orchestrator._low_confidence_reason(
            request.question,
            reranked,
            confidence_metrics.answer_confidence,
            ungrounded_claims=0 if grounding is None or grounding.is_grounded else len(grounding.unsupported),
        )

        # Surface a total now that generate_ms is populated (log only; the
        # stream already emitted the timing dict above).
        total = sum(v for v in timings.values() if isinstance(v, (int, float)))
        timings.setdefault("total_ms", total)

        yield {
            "type": "done",
            # Full source payload with score + rank
            "sources": [_source_payload(chunk) for chunk in reranked],
            "latency_ms": timings,
            # Confidence payload for route to emit as [CONFIDENCE] event
            "confidence": {
                "answer_confidence": confidence_metrics.answer_confidence,
                "source_coverage": confidence_metrics.source_coverage,
                "sources_used": confidence_metrics.sources_used,
                "retrieved_chunks": confidence_metrics.retrieved_chunks,
                "low_confidence_reason": reason,
            },
        }
        logger.info(
            "stream_answer complete: sources=%d latency=%s confidence=%s",
            len(reranked),
            timings,
            confidence_metrics,
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
