"""HTTP routes for Repository Intelligence.

Prefix: ``/repository``.  Analysis is requested with ``POST /analyze`` and
runs in the background; every other endpoint reads a persisted analysis by
its id.  All errors are mapped to clean HTTP responses (no raw stack traces).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_query_service
from app.routes.query import _sse_generator as _query_sse_generator
from app.schemas.query import QueryRequest
from app.services.query_service import QueryService

from .schemas import (
    AnalysisStatus,
    AnalyzeRequest,
    ChangeImpact,
    DataFlow,
    DependencyGraph,
    GitHistory,
    Ownership,
    Repository,
    RepositoryAnalysis,
    RepositoryHealth,
    RiskExplanations,
)
from .service import RepositoryIntelligenceError, RepositoryIntelligenceService
from .chat import ensure_repo_indexed

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repository", tags=["repository-intelligence"])


def _get_service():
    from app.dependencies import get_repository_intelligence_service
    return get_repository_intelligence_service()


def _handle(exc: RepositoryIntelligenceError) -> HTTPException:
    logger.warning("repository intelligence error: %s", exc)
    msg = str(exc)
    if "not found" in msg or "no persisted result" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "not a recognised" in msg.lower():
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


@router.post(
    "/analyze",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a Repository Intelligence analysis",
)
async def analyze(
    request: AnalyzeRequest,
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    """Start an in-background analysis of a public GitHub repository."""
    try:
        return await service.start_analysis(
            request.repo_url, branch=request.branch, force=request.force
        )
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/latest",
    response_model=AnalysisStatus,
    summary="Resolve the latest completed analysis for a repository URL",
)
async def latest(
    repo_url: str = Query(..., description="Public GitHub repository URL"),
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    """Resolve the most recent completed analysis by repository URL.

    Declared before ``/{analysis_id}`` so the static segment wins the route
    match (otherwise ``/latest`` would be captured as an analysis id).
    Useful for the frontend to re-resolve a run after a page refresh.
    """
    try:
        return await service.get_latest_analysis(repo_url)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}",
    response_model=RepositoryAnalysis,
    summary="Fetch the full Repository Intelligence bundle",
)
async def get_analysis(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_analysis(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/status",
    response_model=AnalysisStatus,
    summary="Poll the status of an analysis",
)
async def analysis_status(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_status(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/architecture",
    response_model=DependencyGraph,
    summary="Architecture graph (repo -> area -> dir -> module -> file)",
)
async def architecture(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_architecture(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/dependencies",
    response_model=DependencyGraph,
    summary="Dependency subgraph around a selected node",
)
async def dependencies(
    analysis_id: str,
    selected: str | None = Query(default=None),
    depth: int = Query(default=2, ge=1, le=5),
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    try:
        return await service.get_dependencies(analysis_id, selected, depth=depth)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/data-flow",
    response_model=dict[str, DataFlow],
    summary="Detected execution / data-flow graph for a repository",
)
async def data_flows(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_data_flows(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/git-history",
    response_model=GitHistory,
    summary="Git history, branches, churn and recent commits",
)
async def git_history(
    analysis_id: str,
    range: str = Query(default="180d", alias="range"),
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    try:
        return await service.get_git_history(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/ownership",
    response_model=Ownership,
    summary="Ownership, contributors and bus-factor",
)
async def ownership(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_ownership(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/health",
    response_model=RepositoryHealth,
    summary="Repository health score and dimensions",
)
async def health(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_health(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/repository",
    response_model=Repository,
    summary="Repository header metadata",
)
async def repository(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_repository(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/risk-explanations",
    response_model=RiskExplanations,
    summary="Explainable risk-level descriptions",
)
async def risk_explanations(analysis_id: str, service: RepositoryIntelligenceService = Depends(_get_service)):
    try:
        return await service.get_risk_explanations(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/change-impact",
    response_model=ChangeImpact,
    summary="Blast radius of a change to a given file/module",
)
async def change_impact(
    analysis_id: str,
    path: str = Query(..., description="Repo-relative path of the changed node"),
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    try:
        return await service.get_change_impact(analysis_id, path)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{analysis_id}/node",
    summary="Node / module inspector details",
)
async def node_details(
    analysis_id: str,
    node_id: str = Query(..., description="Node id or repo-relative path"),
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    try:
        return await service.get_module_details(analysis_id, node_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.post(
    "/{analysis_id}/reanalyze",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Force a fresh analysis for a repository",
)
async def reanalyze(
    analysis_id: str,
    service: RepositoryIntelligenceService = Depends(_get_service),
):
    """Re-run analysis with caching disabled for the given repository."""
    try:
        return await service.reanalyze(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc


@router.post(
    "/{analysis_id}/ask",
    status_code=status.HTTP_200_OK,
    summary="Ask a repository-grounded question via SSE streaming",
)
async def ask(
    analysis_id: str,
    request: QueryRequest,
    service: RepositoryIntelligenceService = Depends(_get_service),
    query_service: QueryService = Depends(get_query_service),
) -> StreamingResponse:
    """Stream an answer to a question about this repository.

    The repository is first validated (it must exist and be complete) and
    then the question is forwarded to the ContextForge RAG pipeline, which
    answers from the ingested repository chunks.  Uses the same SSE event
    sequence as ``POST /query/stream`` (tokens + [SOURCES]/[LATENCY]/
    [CONFIDENCE]/[DONE]).
    """
    try:
        await service.get_analysis(analysis_id)
    except RepositoryIntelligenceError as exc:
        raise _handle(exc) from exc

    # Ground the answer in THIS repository: index it into the RAG store on
    # demand (idempotent) and scope the query to its chunks so the answer never
    # leaks content from other sources.
    try:
        scope = await service.get_chat_scope(analysis_id)
        source_id = await ensure_repo_indexed(
            query_service._orchestrator, scope["repo_url"], scope["branch"]
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("repository ask: could not prepare repo context: %s", exc)
        source_id = None

    scoped_request = request.model_copy(update={"source_id": source_id})

    return StreamingResponse(
        _query_sse_generator(scoped_request, query_service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
