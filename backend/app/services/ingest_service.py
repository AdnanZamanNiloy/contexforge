"""
ingest_service.py — Application service for document ingestion workflows.

Bridges the FastAPI route layer and the Orchestrator.  Resolves loaders,
assigns source IDs, and delegates all pipeline logic to Orchestrator.ingest().
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict

from app.schemas.ingest import IngestRequest
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
        loaders: Dict[str, BaseLoader],
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
        # FIX #1 — KeyError → ValueError with a helpful message
        loader = self._resolve_loader(request.source_type)

        source_id = str(uuid.uuid4())
        logger.info(
            "ingest_source: source_type=%s source=%r source_id=%s",
            request.source_type, request.source, source_id,
        )

        try:
            documents = await loader.load(request.source, source_id)
        except Exception as exc:
            logger.error(
                "ingest_source: loader failed for source_id=%s: %s", source_id, exc
            )
            raise RuntimeError(f"Failed to load source '{request.source}': {exc}") from exc

        use_code_chunker = request.source_type == "github"
        chunks_indexed = await self._orchestrator.ingest(documents, use_code_chunker)

        logger.info(
            "ingest_source complete: source_id=%s chunks=%d", source_id, chunks_indexed
        )
        return source_id, chunks_indexed

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
            Tuple of (``source_id``, ``chunks_indexed``).

        Raises:
            ValueError:   If no loader is registered for ``source_type``.
            RuntimeError: If loading or indexing fails.
        """
        # FIX #1 — consistent loader resolution with clear error
        loader = self._resolve_loader(source_type)

        source_id = str(uuid.uuid4())
        logger.info(
            "ingest_file: source_type=%s filename=%r size=%d source_id=%s",
            source_type, filename, len(content), source_id,
        )

        try:
            # FIX #2 — pass (content, source_id, filename) explicitly so file
            # loaders have the filename for metadata without guessing
            documents = await loader.load(content, source_id, filename=filename)
        except Exception as exc:
            logger.error(
                "ingest_file: loader failed for source_id=%s filename=%r: %s",
                source_id, filename, exc,
            )
            raise RuntimeError(f"Failed to load file '{filename}': {exc}") from exc

        chunks_indexed = await self._orchestrator.ingest(documents, use_code_chunker=False)

        logger.info(
            "ingest_file complete: source_id=%s filename=%r chunks=%d",
            source_id, filename, chunks_indexed,
        )
        return source_id, chunks_indexed

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
            raise ValueError(
                f"No loader registered for source_type='{source_type}'. "
                f"Available: {available}"
            )
        return loader