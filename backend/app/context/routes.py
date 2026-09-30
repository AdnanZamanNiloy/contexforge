"""HTTP route for context budgeting.

Prefix: ``/context``.

- ``POST /context/estimate`` — price a source selection without retrieving.

Selecting sources has always been the workspace's main control, but retrieval
kept a fixed handful of chunks whatever was selected, so the choice mostly decided
what was *excluded*.  This endpoint makes the cost of a selection visible while
the user is making it, and reports the gap between the material available and the
material that would actually reach the model.

It runs no embedding, retrieval, rerank or LLM call: it reads the chunk store and
counts tokens, so the UI can call it on every selection change without cost.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.context.estimator import estimate_context
from app.context.schemas import ContextEstimateRequest, ContextEstimateResponse
from app.dependencies import get_orchestrator

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/context", tags=["context"])


@router.post(
    "/estimate",
    response_model=ContextEstimateResponse,
    status_code=status.HTTP_200_OK,
    summary="Estimate the context cost of a source selection",
)
async def estimate_selection(
    payload: ContextEstimateRequest,
    orchestrator=Depends(get_orchestrator),
) -> ContextEstimateResponse:
    """Report what a selection costs and how much of it will be used.

    Cheap by design: no embedding call, no retrieval, no rerank, no generation.
    Raises:
        500: If the chunk store cannot be read.
    """
    try:
        estimate = await estimate_context(
            source_ids=payload.source_ids,
            chunk_index=orchestrator._faiss,
            depth=payload.depth or "focused",
        )
    except Exception as exc:
        logger.error("context estimate failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to estimate context: {exc}",
        ) from exc

    logger.info(
        "context estimate: sources=%d total_tokens=%d prompt_tokens=%d depth=%s effective=%s",
        estimate.source_count,
        estimate.total_token_count,
        estimate.prompt_token_estimate,
        payload.depth or "focused",
        estimate.effective_depth,
    )

    return ContextEstimateResponse(
        source_count=estimate.source_count,
        sources=[
            {
                "source_id": s.source_id,
                "title": s.title,
                "chunk_count": s.chunk_count,
                "char_count": s.char_count,
                "token_count": s.token_count,
            }
            for s in estimate.sources
        ],
        total_char_count=estimate.total_char_count,
        total_token_count=estimate.total_token_count,
        prompt_token_estimate=estimate.prompt_token_estimate,
        prompt_chunk_limit=estimate.prompt_chunk_limit,
        usable_fraction=round(estimate.usable_fraction, 4),
        depth=payload.depth or "focused",
        effective_depth=estimate.effective_depth,
        over_budget=estimate.over_budget,
        beyond_diminishing_returns=estimate.beyond_diminishing_returns,
        dropped_source_ids=estimate.dropped_source_ids,
        missing_source_ids=estimate.missing_source_ids,
    )
