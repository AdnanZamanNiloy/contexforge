"""
routes/query.py — Query endpoints for the ContextForge RAG API.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_query_service
from app.schemas.query import ConfidenceMetrics, QueryRequest, QueryResponse
from app.services.query_service import QueryService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


@router.post(
    "",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a question with cited sources",
)
async def query(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    """Return a complete answer with sources, latency breakdown, and confidence metrics.

    FIX #4 — response now includes ``sources`` and ``latency_ms`` so
    SourceViewer can render citations.

    FIX: response now includes ``confidence`` with server-side ConfidenceMetrics.

    Raises:
        422: If the request body is invalid.
        502: If the pipeline fails.
    """
    logger.info("query: question=%r", request.question)
    try:
        result = await service.answer(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        logger.error("query failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    logger.info(
        "query complete: sources=%d latency=%s confidence=%s",
        len(result.sources),
        result.latency_ms,
        result.confidence,
    )
    # FIX: include confidence in the response
    return QueryResponse(
        answer=result.answer,
        sources=[_chunk_summary(c) for c in result.sources],
        latency_ms=result.latency_ms,
        confidence=(
            ConfidenceMetrics(
                answer_confidence=result.confidence.answer_confidence,
                source_coverage=result.confidence.source_coverage,
                sources_used=result.confidence.sources_used,
                retrieved_chunks=result.confidence.retrieved_chunks,
            )
            if result.confidence
            else None
        ),
    )


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream an answer via Server-Sent Events",
    # No response_model — StreamingResponse bypasses Pydantic serialisation
)
async def stream_query(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> StreamingResponse:
    """Stream answer tokens as Server-Sent Events.

    FIX #1 — each token is wrapped in ``data: ...\\n\\n`` SSE framing so
    the browser's native ``EventSource`` API parses it correctly.

    FIX #3 — ``_sse_generator`` is an async generator; ``StreamingResponse``
    receives it directly (not a coroutine).

    FIX #7 — exceptions mid-stream emit ``data: [ERROR] <msg>\\n\\n`` so
    the client knows the stream ended abnormally rather than silently.

    Event sequence:
        data: <token>\\n\\n          (one per token)
        data: [SOURCES] <json>\\n\\n (source list after last token)
        data: [LATENCY] <json>\\n\\n (per-stage latency breakdown)
        data: [CONFIDENCE] <json>\\n\\n (server-side confidence metrics)
        data: [DONE]\\n\\n           (terminator)
    """
    logger.info("stream_query: question=%r", request.question)
    return StreamingResponse(
        _sse_generator(request, service),
        media_type="text/event-stream",
        headers={
            # Disable buffering so tokens reach the client immediately
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx proxy buffering off
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _sse_generator(request: QueryRequest, service: QueryService):
    """Async generator that yields SSE-formatted strings.

    FIX #1 — wraps every token in ``data: ...\\n\\n``.
    FIX #2 — catches service errors and emits an SSE error event.
    FIX #7 — always terminates with [DONE] or [ERROR].

    FIX: emits ``data: [CONFIDENCE] <json>\\n\\n`` before [DONE].
    """
    try:
        async for payload in service.stream_answer(request):
            if payload.get("type") == "token":
                yield f"data: {payload.get('token', '')}\n\n"
            elif payload.get("type") == "done":
                sources = payload.get("sources", [])
                latency_ms = payload.get("latency_ms", {})
                # FIX: emit confidence event before [DONE]
                confidence = payload.get("confidence")
                yield f"data: [SOURCES] {json.dumps(sources)}\n\n"
                yield f"data: [LATENCY] {json.dumps(latency_ms)}\n\n"
                if confidence is not None:
                    yield f"data: [CONFIDENCE] {json.dumps(confidence)}\n\n"
                yield "data: [DONE]\n\n"
                logger.info("stream_query complete: question=%r", request.question)
                return

        # Fallback if the stream completes without a done event.
        try:
            sources = await service.get_last_sources(request)
            yield f"data: [SOURCES] {json.dumps(sources)}\n\n"
        except Exception as src_exc:
            logger.warning("stream_query: could not attach sources: %s", src_exc)
        yield "data: [DONE]\n\n"
        logger.info("stream_query complete without done event: question=%r", request.question)

    except ValueError as exc:
        logger.warning("stream_query validation error: %s", exc)
        yield f"data: [ERROR] {exc}\n\n"

    except Exception as exc:
        # FIX #7 — mid-stream failure emits a structured error event
        logger.error("stream_query failed mid-stream: %s", exc)
        yield f"data: [ERROR] Generation failed — please retry.\n\n"


def _chunk_summary(chunk) -> dict:
    """Serialise a RerankedChunk to a JSON-safe dict for the API response.

    Extracts the fields SourceViewer needs: chunk_id, text preview,
    source_id, score, rank, and any metadata the loader attached.
    """
    return {
        "chunk_id": chunk.chunk.chunk_id,
        "source_id": chunk.chunk.source_id,
        "score": round(chunk.score, 4),
        "rank": chunk.rank,
        "text_preview": chunk.chunk.text[:200],
        "metadata": dict(chunk.chunk.metadata),
    }
