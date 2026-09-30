"""HTTP routes for Note generation.

Prefix: ``/note``.

- ``GET  /note/{key:path}``  — fetch a previously generated note (404 if none).
- ``POST /note/generate``    — generate (or return the cached) note for a selection.

A *selection* is one source or several, keyed exactly as a mind map is: a single
source keeps its own id so a note generated today is still addressable tomorrow,
and several sources share a sorted composite key.  Reusing that key means a note
and a mind map built from the same selection are cached side by side rather than
under two competing conventions, and the ``:path`` converter lets a
``repo:<owner>/<name>`` key survive the slash in the URL.

Errors are mapped to clean HTTP responses.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_note_service
from app.notes.schemas import GenerateRequest, NoteResponse, split_composite_key
from app.notes.service import NoteError, NoteService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/note", tags=["note"])


@router.post(
    "/generate",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate (or fetch the cached) note for a selection of sources",
)
async def generate(
    request: GenerateRequest,
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Write a note from the selected sources' indexed content.

    Idempotent: if a note already exists for the selection it is returned
    unchanged (201) rather than regenerated.  Pass ``refresh`` to force a
    regeneration after the sources changed.
    """
    try:
        result = await service.generate(request.resolved_source_ids(), refresh=request.refresh)
    except NoteError as exc:
        logger.warning("note generate failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_response(result)


@router.get(
    "/{key:path}",
    response_model=NoteResponse,
    summary="Fetch a previously generated note by source id or selection key",
)
async def get(
    key: str,
    service: NoteService = Depends(get_note_service),
) -> NoteResponse:
    """Return the persisted note for ``key``, or 404 if none exists."""
    result = await service.get(key)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No note has been generated for this source yet.",
        )
    return _to_response(result)


def _to_response(result) -> NoteResponse:
    key = result["source_id"]
    return NoteResponse(
        source_id=key,
        source_ids=result.get("source_ids") or split_composite_key(key),
        title=result.get("title", "Note"),
        markdown=result.get("markdown", ""),
        chunk_count=int(result.get("chunk_count", 0)),
        created_at=result.get("created_at"),
    )
