"""HTTP routes for the Architecture Diagram.

Prefix: ``/architecture``.

- ``POST /architecture/generate``    — generate (or serve cached) as an SSE stream.
- ``GET  /architecture/{project_id}`` — the stored diagram, 404 when none.
- ``POST /architecture/regenerate``  — force a fresh generation, ignoring the cache.

SSE rather than plain JSON because a cold generation spends up to ~55s inside a
model call; a stream lets the client show progress and then receive the finished
artifact, and lets a failure arrive as a readable message instead of an opaque
network timeout.  The frame format matches the existing query stream: a
``[DIAGRAM]`` payload followed by ``[DONE]``, or a single ``[ERROR]``.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.architecture.schemas import (
    ArchitectureGenerateRequest,
    ArchitectureResponse,
)
from app.architecture.service import ArchitectureError, ArchitectureService
from app.dependencies import get_architecture_service, get_ingest_service, get_projects_service
from app.projects.service import ProjectsService
from app.projects.source_resolution import SourceResolutionError, resolve_tool_source
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/architecture", tags=["architecture"])


async def _resolve_source(
    project_id: str,
    explicit_source_id: str | None,
    projects: ProjectsService,
    ingest: IngestService,
) -> str:
    """Resolve the source to map, honouring an explicit per-request choice."""
    inventory: list[dict] = []
    try:
        inventory = (await ingest._orchestrator._faiss.get_source_info()) or []
    except Exception as exc:  # pragma: no cover - storage trouble
        logger.warning("architecture: source inventory unavailable (%s)", exc)
    try:
        resolved = await resolve_tool_source(project_id, explicit_source_id, projects, inventory)
    except SourceResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return resolved.source_id


def _to_payload(record: dict) -> ArchitectureResponse:
    return ArchitectureResponse(
        source_id=record.get("source_id") or "",
        mermaid=record.get("mermaid") or "",
        explanation=record.get("explanation") or "",
        node_count=int(record.get("node_count") or 0),
        edge_count=int(record.get("edge_count") or 0),
        group_count=int(record.get("group_count") or 0),
        repository=record.get("repository") or "",
        branch=record.get("branch") or "main",
        fingerprint=record.get("fingerprint") or "",
        cached=bool(record.get("cached")),
        elapsed_ms=int(record.get("elapsed_ms") or 0),
        truncated_paths=int(record.get("truncated_paths") or 0),
    )


@router.post("/generate", summary="Generate an architecture diagram (SSE)")
async def generate(
    request: ArchitectureGenerateRequest,
    service: ArchitectureService = Depends(get_architecture_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> StreamingResponse:
    """Stream an architecture diagram for the project's selected source.

    Served from cache when the source's indexed files are unchanged; pass
    ``refresh`` (or use ``/regenerate``) to force a new run.
    """
    source_id = await _resolve_source(request.project_id, request.source_id, projects, ingest)

    async def event_stream():
        yield ": architecture diagram\n\n"
        try:
            record = await service.generate(request.project_id, source_id, refresh=request.refresh)
        except ArchitectureError as exc:
            logger.warning("architecture generate failed: %s", exc)
            yield f"data: [ERROR] {json.dumps({'message': str(exc)})}\n\n"
            return
        except Exception:  # pragma: no cover - unexpected
            logger.exception("architecture: unexpected failure")
            yield f"data: [ERROR] {json.dumps({'message': 'Architecture generation failed — please retry.'})}\n\n"
            return

        payload = _to_payload(record).model_dump()
        yield f"data: [DIAGRAM] {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/regenerate", summary="Force a fresh architecture diagram (SSE)")
async def regenerate(
    request: ArchitectureGenerateRequest,
    service: ArchitectureService = Depends(get_architecture_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> StreamingResponse:
    """Regenerate the diagram, ignoring any cached copy."""
    return await generate(
        ArchitectureGenerateRequest(
            project_id=request.project_id,
            source_id=request.source_id,
            refresh=True,
        ),
        service,
        projects,
        ingest,
    )


@router.get("/{project_id}", response_model=ArchitectureResponse, summary="Get a project's stored diagram")
async def get_diagram(
    project_id: str,
    source_id: str = "",
    service: ArchitectureService = Depends(get_architecture_service),
) -> ArchitectureResponse:
    """Return the stored diagram for the project + source, or 404 when none."""
    record = await service.get(project_id, source_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No architecture diagram has been generated for this project yet.",
        )
    return _to_payload({**record, "cached": True})
