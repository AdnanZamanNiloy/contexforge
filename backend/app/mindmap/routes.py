"""HTTP routes for Mind Map generation.

Prefix: ``/mindmap``.

- ``GET  /mindmap/{source_id:path}``  — fetch a previously generated map (404 if none).
- ``POST /mindmap/generate``          — generate (or return the cached) map for a source.

The ``:path`` converter lets ``source_id`` (``repo:<owner>/<name>``) survive the
slash in the URL.  Errors are mapped to clean HTTP responses.
"""
from __future__ import annotations

import logging

from app.dependencies import get_mindmap_service
from app.mindmap.schemas import GenerateRequest, MindMapResponse
from app.mindmap.service import MindMapError, MindMapService
from fastapi import APIRouter, Depends, HTTPException, status

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mindmap", tags=["mind-map"])


def _get_service():
    return get_mindmap_service()


@router.post(
    "/generate",
    response_model=MindMapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate (or fetch the cached) mind map for a source",
)
async def generate(
    request: GenerateRequest,
    service: MindMapService = Depends(_get_service),
) -> MindMapResponse:
    """Generate a mind map from a source's indexed content.

    Idempotent: if a map already exists for ``source_id`` it is returned
    unchanged (200) rather than regenerated.  New maps return 201.
    """
    try:
        result = await service.generate(request.source_id)
    except MindMapError as exc:
        logger.warning("mindmap generate failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _to_response(result)


@router.get(
    "/{source_id:path}",
    response_model=MindMapResponse,
    summary="Fetch a previously generated mind map by source id",
)
async def get(
    source_id: str,
    service: MindMapService = Depends(_get_service),
) -> MindMapResponse:
    """Return the persisted mind map for ``source_id``, or 404 if none exists."""
    result = await service.get(source_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No mind map has been generated for this source yet.",
        )
    return _to_response(result)


def _to_response(result) -> MindMapResponse:
    return MindMapResponse(
        source_id=result["source_id"],
        title=result.get("title", "Mind Map"),
        markdown=result.get("markdown", ""),
        chunk_count=int(result.get("chunk_count", 0)),
        created_at=result.get("created_at"),
    )
