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
from app.security.schemas import SecurityRequest, SecurityResponse
from app.security.service import SecurityError, SecurityService
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


async def _github_source_for_project(
    project_id: str,
    projects: ProjectsService,
    ingest: IngestService,
) -> str:
    """Resolve the project's GitHub source id, or raise 404."""
    inventory: list[dict] = []
    try:
        inventory = (await ingest._orchestrator._faiss.get_source_info()) or []
    except Exception as exc:  # pragma: no cover - storage trouble
        logger.warning("security: source inventory unavailable (%s)", exc)

    project = await projects.get_enriched(project_id, inventory)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")

    by_id = {entry.get("source_id"): entry for entry in inventory if entry.get("source_id")}
    for source_id in project.get("source_ids") or []:
        entry = by_id.get(source_id)
        if not entry:
            continue
        meta = dict(entry.get("metadata") or {})
        source_type = meta.get("source_type") or entry.get("type")
        if source_type == "github" or str(source_id).startswith("repo:"):
            return str(source_id)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Project '{project_id}' has no GitHub source attached. "
            "Attach a repository to it before running a security scan."
        ),
    )


@router.get("/{project_id}", response_model=SecurityResponse, summary="Get a project's stored security scan")
async def get_security(project_id: str, service: SecurityService = Depends(get_security_service)) -> SecurityResponse:
    """Return the stored scan for a project, or 404 when there is none."""
    record = await service.get(project_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No security scan stored for this project yet. Run one to create it.",
        )
    return SecurityResponse(**record)


async def _run(request: SecurityRequest, service: SecurityService, projects: ProjectsService, ingest: IngestService):
    source_id = await _github_source_for_project(request.project_id, projects, ingest)
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
    return await _run(SecurityRequest(project_id=request.project_id, refresh=True), service, projects, ingest)
