"""HTTP routes for the Health Score & Hotspots scan.

Prefix: ``/health``.

- ``GET  /health/{project_id}`` — the stored scan, 404 when none.
- ``POST /health/scan``         — scan, or serve the cached result.
- ``POST /health/rescan``       — force a fresh scan, ignoring the cache.

Plain JSON: the scan is AST parsing of chunks already in memory, so it lands in
milliseconds and there is nothing to stream.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_health_service, get_ingest_service, get_projects_service
from app.health.schemas import HealthRequest, HealthResponse
from app.health.service import HealthError, HealthService
from app.projects.service import ProjectsService
from app.projects.source_resolution import SourceResolutionError, resolve_tool_source
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


async def _resolve_source(
    project_id: str,
    explicit_source_id: str | None,
    projects: ProjectsService,
    ingest: IngestService,
) -> str:
    """Resolve the source to analyse, honouring an explicit per-request choice."""
    inventory: list[dict] = []
    try:
        inventory = (await ingest._orchestrator._faiss.get_source_info()) or []
    except Exception as exc:  # pragma: no cover - storage trouble
        logger.warning("health: source inventory unavailable (%s)", exc)
    try:
        resolved = await resolve_tool_source(project_id, explicit_source_id, projects, inventory)
    except SourceResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return resolved.source_id


@router.get("/{project_id}", response_model=HealthResponse, summary="Get a project's stored health scan")
async def get_scan(
    project_id: str,
    source_id: str = "",
    service: HealthService = Depends(get_health_service),
) -> HealthResponse:
    record = await service.get(project_id, source_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No health scan has been run for this project yet.",
        )
    return HealthResponse(**{**record, "cached": True})


@router.post("/scan", response_model=HealthResponse, summary="Scan a project's structural risk")
async def scan(
    request: HealthRequest,
    service: HealthService = Depends(get_health_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> HealthResponse:
    """Measure structural risk, or return the cached result.

    Idempotent: an unchanged repository is served from cache.  Pass ``refresh``
    to force a rescan.
    """
    source_id = await _resolve_source(request.project_id, request.source_id, projects, ingest)
    try:
        record = await service.scan(request.project_id, source_id, refresh=request.refresh)
    except HealthError as exc:
        logger.warning("health scan failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return HealthResponse(**record)


@router.post("/rescan", response_model=HealthResponse, summary="Force a fresh health scan")
async def rescan(
    request: HealthRequest,
    service: HealthService = Depends(get_health_service),
    projects: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> HealthResponse:
    return await scan(
        HealthRequest(project_id=request.project_id, source_id=request.source_id, refresh=True),
        service,
        projects,
        ingest,
    )
