"""
ingest_service.py — Application service for document ingestion workflows.

Bridges the FastAPI route layer and the Orchestrator.  Resolves loaders,
assigns source IDs, and delegates all pipeline logic to Orchestrator.ingest().

Ingestion is idempotent.  Every source type derives its id from what the source
is rather than from a fresh UUID, so ingesting the same thing twice resolves to
one source and the second run replaces the first.  See
:mod:`app.sources.identity` for the scheme.
"""

from __future__ import annotations

import logging

from app.schemas.ingest import IngestRequest
from app.sources.identity import content_source_id, legacy_source_id_for, url_source_id
from core.ingestion.base_loader import BaseLoader
from core.orchestrator import Orchestrator

__all__ = ["IngestService"]

logger = logging.getLogger(__name__)


class IngestService:
    """Application service for ingestion workflows.

    Args:
        orchestrator: The central RAG pipeline coordinator.
        loaders:      Mapping of ``source_type`` → :class:`BaseLoader`.
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        loaders: dict[str, BaseLoader],
    ) -> None:
        self._orchestrator = orchestrator
        self._loaders = loaders

    async def ingest_source(self, request: IngestRequest) -> tuple[str, int]:
        """Load a remote source and ingest it into the pipeline.

        Args:
            request: Validated :class:`IngestRequest` (source_type + source URL).

        Returns:
            Tuple of (``source_id``, ``chunks_indexed``).

        Raises:
            ValueError:  If no loader is registered for ``source_type``.
            RuntimeError: If loading or indexing fails.
        """
        # KeyError → ValueError with a helpful message
        loader = self._resolve_loader(request.source_type)

        # The id is a function of the source, not of the attempt, so ingesting
        # the same URL again lands on the same source and replaces it.
        source_id = url_source_id(request.source_type, request.source)
        source_id, replaced = await self._adopt_legacy_source(
            source_id,
            source_type=request.source_type,
            url=request.source,
        )
        logger.info(
            "ingest_source: source_type=%s source=%r source_id=%s replacing_existing=%s",
            request.source_type,
            request.source,
            source_id,
            replaced,
        )

        # Loaded *before* the existing chunks are removed. A loader is where
        # ingestion usually fails — a dead link, a rate limit, an unparseable
        # page — and deleting first would turn "that URL did not work" into "that
        # source is gone".
        try:
            documents = await loader.load(request.source, source_id, metadata=request.metadata)
        except Exception as exc:
            logger.error("ingest_source: loader failed for source_id=%s: %s", source_id, exc)
            raise RuntimeError(f"Failed to load source '{request.source}': {exc}") from exc

        # Only now that the replacement content exists in hand is it safe to drop
        # the old chunks. delete_source also clears the deduplicator, without
        # which re-ingesting identical text would be silently rejected.
        if replaced:
            await self._orchestrator.delete_source(source_id)

        use_code_chunker = request.source_type == "github"
        chunks_indexed = await self._orchestrator.ingest(documents, use_code_chunker)

        logger.info(
            "ingest_source complete: source_id=%s chunks=%d replaced=%s",
            source_id,
            chunks_indexed,
            replaced,
        )
        return source_id, chunks_indexed, replaced

    async def ingest_file(
        self,
        source_type: str,
        content: bytes,
        filename: str,
    ) -> tuple[str, int]:
        """Load an uploaded file and ingest it into the pipeline.

        Args:
            source_type: ``"pdf"`` or ``"docx"``.
            content:     Raw file bytes.
            filename:    Original filename (used for metadata and logging).

        Returns:
            Tuple of (``source_id``, ``chunks_indexed``, ``replaced``).

        Raises:
            ValueError:   If no loader is registered for ``source_type``.
            RuntimeError: If loading or indexing fails.
        """
        # Consistent loader resolution with clear error
        loader = self._resolve_loader(source_type)

        # Keyed on the bytes, not the filename: re-uploading the same document
        # updates the existing source instead of adding a second copy, and a file
        # whose contents actually changed is treated as a new document rather
        # than silently overwriting the old one.
        source_id = content_source_id(source_type, content)
        replaced = await self._source_exists(source_id)
        logger.info(
            "ingest_file: source_type=%s filename=%r size=%d source_id=%s replacing_existing=%s",
            source_type,
            filename,
            len(content),
            source_id,
            replaced,
        )

        # Load before deleting, for the same reason as ingest_source: a PDF that
        # will not parse must not cost the user the copy already indexed.
        try:
            # Pass (content, source_id, filename) explicitly so file
            # loaders have the filename for metadata without guessing
            documents = await loader.load(content, source_id, filename=filename)
        except Exception as exc:
            logger.error(
                "ingest_file: loader failed for source_id=%s filename=%r: %s",
                source_id,
                filename,
                exc,
            )
            raise RuntimeError(f"Failed to load file '{filename}': {exc}") from exc

        if replaced:
            await self._orchestrator.delete_source(source_id)

        chunks_indexed = await self._orchestrator.ingest(documents, use_code_chunker=False)

        logger.info(
            "ingest_file complete: source_id=%s filename=%r chunks=%d replaced=%s",
            source_id,
            filename,
            chunks_indexed,
            replaced,
        )
        return source_id, chunks_indexed, replaced

    async def _source_exists(self, source_id: str) -> bool:
        """Whether any chunks are already indexed under *source_id*."""
        try:
            infos = await self._orchestrator.get_source_info()
        except Exception as exc:  # pragma: no cover - store should be readable
            logger.warning("ingest: could not read source info (%s); treating as new", exc)
            return False
        return any((info.get("source_id") or "") == source_id for info in infos or [])

    async def _adopt_legacy_source(
        self,
        source_id: str,
        *,
        source_type: str,
        url: str,
    ) -> tuple[str, bool]:
        """Reconcile a deterministic id with a pre-existing random one.

        Sources ingested before ids were deterministic carry random UUIDs, so a
        deterministic id would not match them. Without this, the first re-ingest
        after the upgrade would leave the old entry behind as a duplicate — the
        exact bug being fixed. When the deterministic id is unused but a stored
        source has the same type and URL, its id is adopted instead, which turns
        the first re-ingest into the repair point.

        Returns:
            ``(source_id, replaced)`` where ``replaced`` is True when the adopted
            id already holds chunks.
        """
        if await self._source_exists(source_id):
            return source_id, True

        legacy = legacy_source_id_for(
            await self._orchestrator.get_source_info(),
            source_type=source_type,
            url=url,
        )
        if not legacy:
            return source_id, False
        if legacy == source_id:
            return source_id, True

        logger.info(
            "ingest: adopting legacy source_id=%s (deterministic id %s was unused)",
            legacy,
            source_id,
        )
        return legacy, await self._source_exists(legacy)

    async def delete_source(self, source_id: str) -> int:
        """Remove all chunks for *source_id* from FAISS and BM25.

        Args:
            source_id: The UUID of the source to delete.

        Returns:
            Number of chunks removed.

        Raises:
            ValueError: If *source_id* is empty.
        """
        if not source_id or not source_id.strip():
            raise ValueError("source_id must not be empty")

        logger.info("delete_source: source_id=%s", source_id)
        chunks_removed = await self._orchestrator.delete_source(source_id)
        logger.info(
            "delete_source complete: source_id=%s chunks_removed=%d",
            source_id,
            chunks_removed,
        )
        return chunks_removed

    async def clear_all(self) -> dict[str, int]:
        """Clear the entire knowledge base (FAISS + BM25 + deduplicator).

        Returns:
            Dict with faiss_chunks_removed and bm25_chunks_removed counts.
        """
        logger.info("clear_all: wiping entire knowledge base")
        result = await self._orchestrator.clear_all()
        logger.info(
            "clear_all complete: faiss=%d bm25=%d",
            result.get("faiss_chunks_removed", 0),
            result.get("bm25_chunks_removed", 0),
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_loader(self, source_type: str) -> BaseLoader:
        """Return the loader for *source_type* or raise :class:`ValueError`.

        FIX #1 — `self._loaders[key]` raises a raw KeyError which becomes
        an unformatted 500.  This converts it to a ValueError that the
        route maps to a clean 422.
        """
        loader = self._loaders.get(source_type)
        if loader is None:
            available = ", ".join(sorted(self._loaders.keys()))
            raise ValueError(f"No loader registered for source_type='{source_type}'. Available: {available}")
        return loader
