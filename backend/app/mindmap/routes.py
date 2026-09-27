"""HTTP routes for Mind Map generation.

Prefix: ``/mindmap``.

- ``GET  /mindmap/{key:path}``  — fetch a previously generated map (404 if none).
- ``POST /mindmap/generate``    — generate (or return the cached) map for a selection.

A *selection* is one source or several.  A single source is keyed by its own id
so every map generated before multi-source support stays addressable; several
sources are keyed by a sorted composite key.  The ``:path`` converter lets those
keys (``repo:<owner>/<name>``) survive the slash in the URL.  Errors are mapped
to clean HTTP responses.
"""
from __future__ import annotations

import logging

from app.dependencies import get_mindmap_service
from app.mindmap.schemas import GenerateRequest, MindMapResponse, split_composite_key
from app.mindmap.service import MindMapError, MindMapService
from fastapi import APIRouter, Depends, HTTPException, status

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mindmap", tags=["mind-map"])


@router.post(
    "/generate",
    response_model=MindMapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate (or fetch the cached) mind map for a selection of sources",
)
async def generate(
    request: GenerateRequest,
    service: MindMapService = Depends(get_mindmap_service),
) -> MindMapResponse:
    """Generate a mind map from the selected sources' indexed content.

    Idempotent: if a map already exists for the selection it is returned
    unchanged (201) rather than regenerated.  Pass ``refresh`` to force a
    regeneration after the sources changed.
    """
    try:
        result = await service.generate(
            request.resolved_source_ids(), refresh=request.refresh
        )
    except MindMapError as exc:
        logger.warning("mindmap generate failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _to_response(result)


@router.get(
    "/{key:path}",
    response_model=MindMapResponse,
    summary="Fetch a previously generated mind map by source id or selection key",
)
async def get(
    key: str,
    service: MindMapService = Depends(get_mindmap_service),
) -> MindMapResponse:
    """Return the persisted mind map for ``key``, or 404 if none exists."""
    result = await service.get(key)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No mind map has been generated for this source yet.",
        )
    return _to_response(result)


def _to_response(result) -> MindMapResponse:
    key = result["source_id"]
    return MindMapResponse(
        source_id=key,
        source_ids=result.get("source_ids") or split_composite_key(key),
        title=result.get("title", "Mind Map"),
        markdown=result.get("markdown", ""),
        chunk_count=int(result.get("chunk_count", 0)),
        created_at=result.get("created_at"),
    )
