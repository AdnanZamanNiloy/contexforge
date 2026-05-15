"""
routes/ingest.py — Ingestion endpoints for the ContextForge API.

Endpoints:
    POST /ingest/source  — Ingest a URL or GitHub repo by reference.
    POST /ingest/file    — Upload and ingest a PDF or DOCX file.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import status

from app.dependencies import get_ingest_service
from app.schemas.ingest import IngestRequest, IngestResponse
from app.services.ingest_service import IngestService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

#  hard limit: 50 MB per upload (bytes)
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# allowed MIME types per source_type
_ALLOWED_MIME: dict[str, set[str]] = {
    "pdf":  {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    },
}



@router.post(
    "/source",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a URL or GitHub repository",
)
async def ingest_source(
    request: IngestRequest,
    service: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
    """Ingest a remote source (web URL or GitHub repo) by reference.
    """
    logger.info("ingest_source: source_url=%s", getattr(request, "source_url", "?"))
    try:
        source_id, chunks_indexed = await service.ingest_source(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        logger.error("ingest_source failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    logger.info(
        "ingest_source complete: source_id=%s chunks=%d", source_id, chunks_indexed
    )
    return IngestResponse(source_id=source_id, chunks_indexed=chunks_indexed)


@router.post(
    "/file",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload and ingest a PDF or DOCX file",
)
async def ingest_file(
    source_type: Literal["pdf", "docx"],
    upload: UploadFile = File(...),
    service: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
 
    filename = upload.filename
    if not filename or not filename.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file must have a filename.",
        )

    content_type = upload.content_type or ""
    allowed_mime = _ALLOWED_MIME[source_type]
    if content_type not in allowed_mime:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Expected content-type {allowed_mime} for source_type '{source_type}', "
                f"got '{content_type}'."
            ),
        )


    content = await _read_with_limit(upload, _MAX_UPLOAD_BYTES)

    logger.info(
        "ingest_file: filename=%s source_type=%s size=%d bytes",
        filename, source_type, len(content),
    )


    try:
        source_id, chunks_indexed = await service.ingest_file(
            source_type, content, filename
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        logger.error("ingest_file failed for '%s': %s", filename, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    logger.info(
        "ingest_file complete: source_id=%s filename=%s chunks=%d",
        source_id, filename, chunks_indexed,
    )
    return IngestResponse(source_id=source_id, chunks_indexed=chunks_indexed)


async def _read_with_limit(upload: UploadFile, max_bytes: int) -> bytes:
    """Read *upload* up to *max_bytes*, raising HTTP 413 if exceeded."""
    chunks: list[bytes] = []
    total = 0
    chunk_size = 65_536  # 64 KB

    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit.",
            )
        chunks.append(chunk)

    return b"".join(chunks)