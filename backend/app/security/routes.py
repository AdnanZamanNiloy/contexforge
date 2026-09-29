"""HTTP routes for the Security & Quality scan.

Prefix: ``/security``.

- ``GET  /security/{project_id}`` — the stored scan, 404 when none.
- ``POST /security/scan``         — scan, or serve the cached result.
- ``POST /security/rescan``       — force a fresh scan, ignoring the cache.

Plain JSON rather than SSE.  The code half is a subprocess over a few hundred
files and the dependency half is a handful of small HTTP calls, so the scan is
seconds rather than minutes -- but it is not the millisecond work the tech stack
scan is, so the endpoint is allowed to be slower without pretending otherwise.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_ingest_service, get_projects_service, get_security_service
from app.projects.service import ProjectsService
from app.projects.source_resolution import SourceResolutionError, resolve_tool_source
from app.security.schemas import SecurityRequest, SecurityResponse
from app.security.service import SecurityError, SecurityService
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


async def _resolve_source(
    project_id: str,
    explicit_source_id: str | None,
    projects: ProjectsService,
    ingest: IngestService,
) -> str:
    """Resolve the source to scan, honouring an explicit per-request choice."""
    inventory: list[dict] = []
    try:
        inventory = (await ingest._orchestrator._faiss.get_source_info()) or []
    except Exception as exc:  # pragma: no cover - storage trouble
        logger.warning("security: source inventory unavailable (%s)", exc)
    try:
        resolved = await resolve_tool_source(project_id, explicit_source_id, projects, inventory)
    except SourceResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return resolved.source_id


@router.get("/{project_id}", response_model=SecurityResponse, summary="Get a project's stored security scan")
async def get_security(
    project_id: str,
    source_id: str = "",
    service: SecurityService = Depends(get_security_service),
) -> SecurityResponse:
    """Return the stored scan for the project + source, or 404 when none."""
    record = await service.get(project_id, source_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No security scan stored for this project yet. Run one to create it.",
        )
    return SecurityResponse(**record)


async def _run(request: SecurityRequest, service: SecurityService, projects: ProjectsService, ingest: IngestService):
    source_id = await _resolve_source(request.project_id, request.source_id, projects, ingest)
    try:
        record = await service.scan(request.project_id, source_id, refresh=request.refresh)
    except SecurityError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return SecurityResponse(**record)


@router.post("/scan", response_model=SecurityResponse, summary="Scan a project's security and quality posture")
async def scan_security(
    request: SecurityRequest,
    service: SecurityService = Depends(get_security_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> SecurityResponse:
    """Scan the project's indexed GitHub source, or serve the cached result."""
    return await _run(request, service, projects, ingest)


@router.post("/rescan", response_model=SecurityResponse, summary="Force a fresh security scan")
async def rescan_security(
    request: SecurityRequest,
    service: SecurityService = Depends(get_security_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> SecurityResponse:
    """Rescan from scratch, ignoring the cache."""
    return await _run(
        SecurityRequest(project_id=request.project_id, source_id=request.source_id, refresh=True),
        service,
        projects,
        ingest,
    )
