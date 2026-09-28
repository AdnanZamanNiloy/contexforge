"""HTTP routes for the Dependency & Tech Stack scan.

Prefix: ``/tech-stack``.

- ``GET  /tech-stack/{project_id}`` — the stored scan, 404 when none.
- ``POST /tech-stack/scan``         — scan, or serve the cached result.
- ``POST /tech-stack/rescan``       — force a fresh scan, ignoring the cache.

Plain JSON rather than SSE: the scan is local string processing over chunks that
are already in memory, so it finishes in milliseconds.  Streaming would add a
client and a transport for a response that is ready before a stream could be
established.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_ingest_service, get_projects_service, get_techstack_service
from app.projects.service import ProjectsService
from app.services.ingest_service import IngestService
from app.techstack.schemas import TechStackRequest, TechStackResponse
from app.techstack.service import TechStackError, TechStackService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tech-stack", tags=["tech-stack"])


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
        logger.warning("techstack: source inventory unavailable (%s)", exc)

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
        detail="This project has no GitHub source to scan.",
    )


@router.get("/{project_id}", response_model=TechStackResponse, summary="Get a project's stored tech stack scan")
async def get_scan(
    project_id: str,
    service: TechStackService = Depends(get_techstack_service),
) -> TechStackResponse:
    """Return the project's stored scan, or 404 when none has been run."""
    record = await service.get(project_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tech stack scan has been run for this project yet.",
        )
    return TechStackResponse(**{**record, "cached": True})


@router.post("/scan", response_model=TechStackResponse, summary="Scan a project's tech stack")
async def scan(
    request: TechStackRequest,
    service: TechStackService = Depends(get_techstack_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> TechStackResponse:
    """Scan manifests and lockfiles, or return the cached result.

    Idempotent: an unchanged repository is served from cache.  Pass ``refresh``
    to force a rescan.
    """
    source_id = await _github_source_for_project(request.project_id, projects, ingest)
    try:
        record = await service.scan(request.project_id, source_id, refresh=request.refresh)
    except TechStackError as exc:
        logger.warning("techstack scan failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TechStackResponse(**record)


@router.post("/rescan", response_model=TechStackResponse, summary="Force a fresh tech stack scan")
async def rescan(
    request: TechStackRequest,
    service: TechStackService = Depends(get_techstack_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> TechStackResponse:
    """Rescan, ignoring any cached copy."""
    return await scan(TechStackRequest(project_id=request.project_id, refresh=True), service, projects, ingest)
