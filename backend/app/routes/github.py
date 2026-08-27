"""
routes/github.py — GitHub repository ingestion endpoint.

Endpoint:
    POST /github/ingest — Validate and ingest a public GitHub repository.
"""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_ingest_service
from app.schemas.github import GithubIngestRequest
from app.schemas.ingest import IngestRequest, IngestResponse
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

# Only accept canonical GitHub repo URLs
# Matches: https://github.com/owner/repo  (with or without trailing slash / .git)
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/[\w.\-]+/[\w.\-]+(\.git)?/?$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a public GitHub repository",
)
async def ingest_github(
    # Dedicated schema instead of abusing IngestRequest with a hardcoded source_type
    request: GithubIngestRequest,
    service: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
    """Clone and ingest all supported files from a GitHub repository.

    The loader hard-limits to 500 files and skips binaries and lock files
    as defined in ``settings.MAX_GITHUB_FILES``.

    Args:
        request: Body containing ``repo_url`` and optional ``branch``.

    Returns:
        Assigned ``source_id`` and ``chunks_indexed`` count.

    Raises:
        422: If ``repo_url`` is not a valid GitHub repository URL.
        502: If cloning or ingestion fails.
    """
    # Validate URL shape before it reaches the loader
    if not _GITHUB_URL_RE.match(request.repo_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{request.repo_url}' is not a valid GitHub repository URL. "
                "Expected format: https://github.com/owner/repo"
            ),
        )

    logger.info("ingest_github: repo_url=%s branch=%s", request.repo_url, request.branch)

    # Map service errors to clean HTTP responses.
    # The RAG ingest is best-effort: a failure here (e.g. the embedding
    # service being rate-limited) must not block the Repository Intelligence
    # analysis, which is the primary deliverable for GitHub sources.
    source_id: str | None = None
    chunks_indexed = 0
    rag_message = ""
    try:
        # The service expects an IngestRequest (source_type + source).
        # Re-map the dedicated schema to it, keeping the dedicated validation
        # above (which rejects non-canonical GitHub URLs before this point).
        ingest_request = IngestRequest(
            source_type="github",
            source=request.repo_url,
            metadata={"branch": request.branch} if request.branch else None,
        )
        source_id, chunks_indexed = await service.ingest_source(ingest_request)
        rag_message = f"Successfully indexed {chunks_indexed} chunk{'s' if chunks_indexed != 1 else ''}."
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning(
            "ingest_github: knowledge-base ingest failed for '%s': %s",
            request.repo_url,
            exc,
        )
        rag_message = "Knowledge-base indexing skipped (embedding service unavailable)."

    if source_id is None:
        source_id = str(uuid.uuid4())

    # Auto-trigger Repository Intelligence analysis for the ingested repo.
    # Best-effort: analysis failures must not fail the ingest response.
    analysis_id = None
    try:
        from app.dependencies import get_repository_intelligence_service

        analysis = await get_repository_intelligence_service().start_analysis(request.repo_url, branch=request.branch)
        analysis_id = analysis.get("analysis_id")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not auto-start repository intelligence for %s: %s",
            request.repo_url,
            exc,
        )

    message = rag_message
    if analysis_id:
        message += " Repository Intelligence analysis started."
    else:
        message += " Repository Intelligence analysis was not started."

    return IngestResponse(
        source_id=source_id,
        chunks_indexed=chunks_indexed,
        analysis_id=analysis_id,
        message=message,
    )
