"""
routes/github.py — GitHub repository ingestion endpoint.

Endpoint:
    POST /github/ingest — Validate and ingest a public GitHub repository.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_ingest_service
from app.schemas.ingest import IngestResponse
from app.schemas.github import GithubIngestRequest
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

# FIX #4 — only accept canonical GitHub repo URLs
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
    # FIX #3 — dedicated schema instead of abusing IngestRequest with a hardcoded source_type
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
    # FIX #1/#4 — validate URL shape before it reaches the loader
    if not _GITHUB_URL_RE.match(request.repo_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{request.repo_url}' is not a valid GitHub repository URL. "
                "Expected format: https://github.com/owner/repo"
            ),
        )

    logger.info("ingest_github: repo_url=%s branch=%s", request.repo_url, request.branch)

    # FIX #2 — map service errors to clean HTTP responses
    try:
        source_id, chunks_indexed = await service.ingest_source(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except RuntimeError as exc:
        logger.error("ingest_github failed for '%s': %s", request.repo_url, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        )

    # FIX #5 — log completion with key metrics
    logger.info(
        "ingest_github complete: source_id=%s repo=%s chunks=%d",
        source_id, request.repo_url, chunks_indexed,
    )
    return IngestResponse(source_id=source_id, chunks_indexed=chunks_indexed)