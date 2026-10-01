"""
routes/ingest.py — Ingestion endpoints for the ContextForge API.

Endpoints:
    POST /ingest/source           — Ingest a URL or GitHub repo by reference.
    POST /ingest/file             — Upload and ingest a PDF or DOCX file.
    PATCH /ingest/source/{id}     — Rename a source (persist a title override).
    DELETE /ingest/source/{id}    — Delete a previously ingested source.
    GET /ingest/sources           — List current source/chunk counts.
    GET /ingest/source/{id}       — Inspect one source: metadata and extraction stats.
    GET /ingest/source/{id}/content — The indexed chunk text for one source.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.dependencies import get_ingest_service, get_source_meta_store
from app.schemas.ingest import (
    DeleteResponse,
    IngestRequest,
    IngestResponse,
    SourcesResponse,
)
from app.services.ingest_service import IngestService
from app.sources.inspection import build_source_content, build_source_detail
from app.sources.schemas import (
    SourceContentResponse,
    SourceDetailResponse,
    UpdateSourceRequest,
    UpdateSourceResponse,
)
from app.sources.storage import SourceMetaStore

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

#  hard limit: 50 MB per upload (bytes)
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# allowed MIME types per source_type
_ALLOWED_MIME: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
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
    """Ingest a remote source (web URL or GitHub repo) by reference."""
    logger.info("ingest_source: source_type=%s source=%s", request.source_type, request.source)
    try:
        source_id, chunks_indexed, replaced = await service.ingest_source(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("ingest_source failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    logger.info("ingest_source complete: source_id=%s chunks=%d replaced=%s", source_id, chunks_indexed, replaced)
    return IngestResponse(source_id=source_id, chunks_indexed=chunks_indexed, replaced=replaced)


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
            detail=(f"Expected content-type {allowed_mime} for source_type '{source_type}', got '{content_type}'."),
        )

    content = await _read_with_limit(upload, _MAX_UPLOAD_BYTES)

    logger.info(
        "ingest_file: filename=%s source_type=%s size=%d bytes",
        filename,
        source_type,
        len(content),
    )

    try:
        source_id, chunks_indexed, replaced = await service.ingest_file(source_type, content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("ingest_file failed for '%s': %s", filename, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    logger.info(
        "ingest_file complete: source_id=%s filename=%s chunks=%d replaced=%s",
        source_id,
        filename,
        chunks_indexed,
        replaced,
    )
    return IngestResponse(source_id=source_id, chunks_indexed=chunks_indexed, replaced=replaced)


@router.patch(
    "/source/{source_id:path}",
    response_model=UpdateSourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Rename a source",
)
async def update_source(
    source_id: str,
    payload: UpdateSourceRequest,
    meta_store: SourceMetaStore = Depends(get_source_meta_store),
) -> UpdateSourceResponse:
    """Persist a custom display title for *source_id*.

    A source's title is derived from its chunk metadata, which lives in
    FAISS/BM25.  Renaming therefore records an override in a small side store
    that ``GET /ingest/sources`` layers over the derived title, so no chunk
    rows are rewritten and the name survives a restart.
    """
    if not source_id or not source_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_id must not be blank or whitespace-only",
        )
    logger.info("update_source: source_id=%s", source_id)
    try:
        result = await meta_store.set_title(source_id.strip(), payload.title)
    except Exception as exc:
        logger.exception("update_source failed for source_id=%s", source_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rename source: {exc}",
        ) from exc
    return UpdateSourceResponse(**result)


@router.delete(
    "/source/{source_id:path}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a previously ingested source",
)
async def delete_source(
    source_id: str,
    service: IngestService = Depends(get_ingest_service),
    meta_store: SourceMetaStore = Depends(get_source_meta_store),
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
        ) from exc

    # Keep the Projects library in sync — a deleted source must not linger on
    # any project card.  Best-effort so a projects-store hiccup never blocks
    # the authoritative FAISS/BM25 delete.
    try:
        from app.dependencies import get_projects_store

        await get_projects_store().remove_source_everywhere(source_id)
    except Exception as exc:
        logger.warning("delete_source: projects unsubscribe failed for %s: %s", source_id, exc)

    # A rename is meaningless once the source is gone, and a re-ingest would
    # derive a fresh title anyway.
    try:
        await meta_store.clear(source_id)
    except Exception as exc:
        logger.warning("delete_source: title override cleanup failed for %s: %s", source_id, exc)

    logger.info(
        "delete_source complete: source_id=%s chunks_deleted=%d",
        source_id,
        chunks_deleted,
    )
    return DeleteResponse(source_id=source_id, chunks_deleted=chunks_deleted)


@router.get(
    "/sources",
    response_model=SourcesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current source/chunk counts",
)
async def get_sources(
    service: IngestService = Depends(get_ingest_service),
    meta_store: SourceMetaStore = Depends(get_source_meta_store),
) -> SourcesResponse:
    """Return the current number of chunks and grouped source info from the store.

    Titles are derived from chunk metadata in FAISS; any rename the user made is
    layered on top from the source-meta side store.
    """
    try:
        # Via the orchestrator rather than its FAISS store, which is private.
        bm25 = service._orchestrator._bm25
        sources = await service._orchestrator.get_source_info()
        total_chunks = await bm25.count()
        overrides = await meta_store.all_titles()
        for source in sources:
            custom = overrides.get(source.get("source_id"))
            if custom:
                source["title"] = custom
        logger.info(
            "get_sources: found %d source groups, %d total chunks, %d renamed",
            len(sources),
            total_chunks,
            len(overrides),
        )
    except Exception as exc:
        logger.error("get_sources failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sources: {exc}",
        ) from exc

    return SourcesResponse(total_chunks=total_chunks, sources=sources)


def _require_source_id(source_id: str) -> None:
    """Reject a blank source id before it reaches the index lookup."""
    if not source_id or not source_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source_id must not be empty.",
        )


async def _source_chunks(service: IngestService, source_id: str):
    """Every indexed chunk for *source_id*, or 404 when the source is unknown."""
    chunks = await service._orchestrator._faiss.get_chunks_by_source_id(source_id)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' is not in the index.",
        )
    return chunks


def _derived_title(chunks) -> str:
    """The source's loader-derived title, matching how the list resolves it.

    The list groups by source id and keeps whichever title it saw first, so a
    repository resolves to ``repo`` rather than to the title of whichever file
    happened to be indexed first — which for a repo is usually LICENSE.
    """
    meta = chunks[0].metadata or {}
    if str(meta.get("source_type") or meta.get("source") or "") == "github" and meta.get("repo"):
        return str(meta["repo"])
    return str(meta.get("title") or "Untitled source")


# NOTE: this route is declared before the `{source_id:path}` detail route on
# purpose. `path` is greedy, so `/source/{id:path}` would otherwise swallow a
# trailing `/content` and report the whole thing as an unknown source id. FastAPI
# matches in declaration order, so the more specific route has to come first.
@router.get(
    "/source/{source_id:path}/content",
    response_model=SourceContentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the indexed chunk text for one source",
)
async def get_source_content(
    source_id: str,
    service: IngestService = Depends(get_ingest_service),
) -> SourceContentResponse:
    """Return the chunk text retrieval actually holds for *source_id*.

    This is the index's view, not the original document: what a user reads here
    is exactly what can be retrieved and quoted. Chunks are capped, and
    ``truncated`` reports when a long source was cut.

    Raises:
        404: If the source is not in the index.
    """
    _require_source_id(source_id)

    try:
        chunks = await _source_chunks(service, source_id)
        content = build_source_content(chunks, source_id=source_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_source_content failed for source_id=%s: %s", source_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read source '{source_id}': {exc}",
        ) from exc

    return content


@router.get(
    "/source/{source_id:path}",
    response_model=SourceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect one ingested source",
)
async def get_source_detail(
    source_id: str,
    service: IngestService = Depends(get_ingest_service),
    meta_store: SourceMetaStore = Depends(get_source_meta_store),
) -> SourceDetailResponse:
    """Describe a single source: how it was labelled and what was indexed.

    Answers the question the source list cannot: *did the extraction actually
    work?* A scanned PDF with no text layer, a DOCX that lost its tables, or a
    fetch that captured navigation instead of the article all still produce a
    source that appears in the sidebar and answers questions.

    Raises:
        404: If the source is not in the index.
    """
    _require_source_id(source_id)

    try:
        chunks = await _source_chunks(service, source_id)
        overrides = await meta_store.all_titles()
        detail = build_source_detail(
            chunks,
            source_id=source_id,
            derived_title=_derived_title(chunks),
            title_override=overrides.get(source_id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_source_detail failed for source_id=%s: %s", source_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to inspect source '{source_id}': {exc}",
        ) from exc

    logger.info(
        "get_source_detail: source_id=%s type=%s chunks=%d chars=%d renamed=%s",
        source_id,
        detail.source_type,
        detail.chunk_count,
        detail.char_count,
        detail.renamed,
    )
    return detail


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
