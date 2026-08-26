"""
routes/ingest.py — Ingestion endpoints for the ContextForge API.

Endpoints:
    POST /ingest/source           — Ingest a URL or GitHub repo by reference.
    POST /ingest/file             — Upload and ingest a PDF or DOCX file.
    DELETE /ingest/source/{id}    — Delete a previously ingested source.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import status

from app.dependencies import get_ingest_service
from app.schemas.ingest import ClearResponse, DeleteResponse, IngestRequest, IngestResponse, SourcesResponse
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
    logger.info("ingest_source: source_type=%s source=%s", request.source_type, request.source)
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


@router.delete(
    "/source/{source_id:path}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a previously ingested source",
)
async def delete_source(
    source_id: str,
    service: IngestService = Depends(get_ingest_service),
) -> DeleteResponse:
    """Remove all chunks belonging to *source_id* from FAISS and BM25.

    After deletion the system behaves as if the source was never ingested.
    Subsequent queries will no longer return chunks from this source.

    Args:
        source_id: UUID of the source to delete.

    Returns:
        Deletion confirmation with chunks_deleted count.

    Raises:
        422: If source_id is empty.
        500: If deletion fails unexpectedly.
    """
    logger.info("delete_source: source_id=%s", source_id)

    if not source_id or not source_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_id must not be empty.",
        )

    try:
        chunks_deleted = await service.delete_source(source_id)
    except Exception as exc:
        logger.error("delete_source failed for source_id=%s: %s", source_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete source '{source_id}': {exc}",
        )

    logger.info(
        "delete_source complete: source_id=%s chunks_deleted=%d",
        source_id, chunks_deleted,
    )
    return DeleteResponse(source_id=source_id, chunks_deleted=chunks_deleted)


@router.delete(
    "/clear",
    response_model=ClearResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear the entire knowledge base",
)
async def clear_knowledge_base(
    service: IngestService = Depends(get_ingest_service),
) -> ClearResponse:
    """Wipe all FAISS vectors, BM25 entries, and the deduplicator.

    Use with caution — this is irreversible.
    """
    logger.info("clear_knowledge_base: wiping all data")
    try:
        result = await service.clear_all()
    except Exception as exc:
        logger.error("clear_knowledge_base failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear knowledge base: {exc}",
        )

    total = result.get("faiss_chunks_removed", 0) + result.get("bm25_chunks_removed", 0)
    logger.info("clear_knowledge_base complete: removed %d total chunks", total)
    return ClearResponse(
        message=f"Knowledge base cleared. Removed {total} chunks.",
        faiss_chunks_removed=result.get("faiss_chunks_removed", 0),
        bm25_chunks_removed=result.get("bm25_chunks_removed", 0),
    )


@router.get(
    "/sources",
    response_model=SourcesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current source/chunk counts",
)
async def get_sources(
    service: IngestService = Depends(get_ingest_service),
) -> SourcesResponse:
    """Return the current number of chunks and grouped source info from the store."""
    try:
        faiss_store = service._orchestrator._faiss
        bm25 = service._orchestrator._bm25
        sources = await faiss_store.get_source_info()
        total_chunks = await bm25.count()
        logger.info("get_sources: found %d source groups, %d total chunks", len(sources), total_chunks)
    except Exception as exc:
        logger.error("get_sources failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sources: {exc}",
        )

    return SourcesResponse(total_chunks=total_chunks, sources=sources)


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