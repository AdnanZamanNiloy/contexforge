"""HTTP routes for the Projects library.

Prefix: ``/projects``.  Metadata + membership live in SQLite; source counts
are reconciled against the live FAISS inventory on every read so the library
never shows stale numbers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.chat.service import ChatService
from app.dependencies import get_chat_service, get_ingest_service, get_projects_service
from app.services.ingest_service import IngestService

from .schemas import (
    AttachSourceRequest,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
    SetToolSourceRequest,
)
from .service import ProjectsService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


async def _inventory(ingest: IngestService) -> list[dict]:
    """Best-effort live source inventory; empty on storage errors."""
    try:
        faiss_store = ingest._orchestrator._faiss
        sources = await faiss_store.get_source_info()
        return sources or []
    except Exception as exc:
        logger.warning("projects: inventory unavailable (%s)", exc)
        return []


@router.get("", response_model=ProjectListResponse, summary="List all projects")
async def list_projects(
    service: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> ProjectListResponse:
    inventory = await _inventory(ingest)
    projects = await service.list_enriched(inventory)
    return ProjectListResponse(
        projects=[ProjectResponse(**p) for p in projects],
        total=len(projects),
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create a project")
async def create_project(
    payload: ProjectCreate,
    service: ProjectsService = Depends(get_projects_service),
) -> ProjectResponse:
    project = await service.create(payload.name, payload.description, payload.category, payload.source_category)
    return ProjectResponse(**project)


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get one project")
async def get_project(
    project_id: str,
    service: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> ProjectResponse:
    inventory = await _inventory(ingest)
    project = await service.get_enriched(project_id, inventory)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ProjectResponse(**project)


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Rename / edit a project")
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    service: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> ProjectResponse:
    try:
        updated = await service.update(
            project_id,
            {
                "name": payload.name,
                "description": payload.description,
                "category": payload.category,
                "source_category": payload.source_category,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    inventory = await _inventory(ingest)
    enriched = await service.get_enriched(project_id, inventory)
    return ProjectResponse(**(enriched or updated))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a project")
async def delete_project(
    project_id: str,
    service: ProjectsService = Depends(get_projects_service),
    chat: ChatService = Depends(get_chat_service),
) -> None:
    # Purge the project's chat history first.  Deleting the project is the only
    # event that removes a session, so sessions must not survive their parent;
    # doing it before the project row goes means a failure here leaves the
    # project (and its history) intact rather than orphaning sessions.
    try:
        removed = await chat.delete_for_project(project_id)
        logger.info("delete_project: removed %d chat session(s) for %s", removed, project_id)
    except Exception as exc:
        logger.warning("delete_project: chat cleanup failed for %s: %s", project_id, exc)

    ok = await service.delete(project_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return None


@router.put(
    "/{project_id}/tool-source",
    response_model=ProjectResponse,
    summary="Set the source the Studio analysis tools target",
)
async def set_tool_source(
    project_id: str,
    payload: SetToolSourceRequest,
    service: ProjectsService = Depends(get_projects_service),
) -> ProjectResponse:
    project = await service.set_tool_source(project_id, payload.source_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ProjectResponse(**project)


@router.post("/{project_id}/touch", response_model=ProjectResponse, summary="Mark a project as opened")
async def touch_project(
    project_id: str,
    service: ProjectsService = Depends(get_projects_service),
) -> ProjectResponse:
    project = await service.touch(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ProjectResponse(**project)


@router.post("/{project_id}/sources", response_model=ProjectResponse, summary="Attach a source to a project")
async def attach_source(
    project_id: str,
    payload: AttachSourceRequest,
    service: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> ProjectResponse:
    ok = await service.attach(project_id, payload.source_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    inventory = await _inventory(ingest)
    project = await service.get_enriched(project_id, inventory)
    return ProjectResponse(**project)


@router.delete(
    "/{project_id}/sources/{source_id}",
    response_model=ProjectResponse,
    summary="Detach a source from a project",
)
async def detach_source(
    project_id: str,
    source_id: str,
    service: ProjectsService = Depends(get_projects_service),
    ingest: IngestService = Depends(get_ingest_service),
) -> ProjectResponse:
    await service.detach(project_id, source_id)
    inventory = await _inventory(ingest)
    project = await service.get_enriched(project_id, inventory)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ProjectResponse(**project)
