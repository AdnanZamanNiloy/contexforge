from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import List

import numpy as np

from app.config.settings import settings
from core.types import Chunk, RetrievedChunk
from observability.tracer import observe

__all__ = ["FaissStore"]

logger = logging.getLogger(__name__)


class FaissStore:

    def __init__(self, index_path: Path | None = None) -> None:
        self._index_path: Path = Path(index_path or settings.FAISS_INDEX_PATH)
        self._metadata_path: Path = self._index_path.with_suffix(".json")

        self._index = None
        self._faiss = None
        self._chunks: List[Chunk] = []
        self._load_lock = asyncio.Lock()
        self._loaded = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="faiss_add")
    async def add(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks ({len(chunks)}) and vectors ({len(vectors)}) length mismatch"
            )
        if not vectors:
            logger.debug("faiss_add called with empty vectors — nothing to do.")
            return

        dimension = len(vectors[0])
        await self._ensure_loaded(dimension)
        await asyncio.to_thread(self._add_sync, chunks, vectors)

    @observe(name="faiss_search")
    async def search(self, query_vector: List[float], top_k: int) -> List[RetrievedChunk]:
        if not query_vector:
            raise ValueError("query_vector must not be empty")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        await self._ensure_loaded(len(query_vector))

        if self._index is None or self._index.ntotal == 0:
            logger.debug("FAISS index is empty — returning no results.")
            return []

        effective_top_k = min(top_k, self._index.ntotal)
        if effective_top_k < top_k:
            logger.debug(
                "top_k=%d clamped to index size %d.", top_k, effective_top_k
            )

        return await asyncio.to_thread(self._search_sync, query_vector, effective_top_k)

    @observe(name="faiss_delete_by_source")
    async def delete_by_source_id(self, source_id: str) -> int:
        """Remove all chunks belonging to *source_id* from the FAISS index.

        FAISS IndexFlatIP does not support native deletion, so this method
        rebuilds the index from scratch excluding the deleted chunks.
        Persists atomically (write-to-temp + rename) so a crash during
        save never leaves a half-written index on disk.

        Returns:
            Number of chunks removed.
        """
        if not source_id:
            raise ValueError("source_id must not be empty")

        await self._ensure_loaded(None)

        if self._index is None or not self._chunks:
            logger.debug("delete_by_source_id: index empty — nothing to delete.")
            return 0

        return await asyncio.to_thread(self._delete_by_source_id_sync, source_id)

    async def force_reload(self) -> None:
        """Discard in-memory state and reload from disk on next operation.

        Call this after an external modification (e.g. delete + persist) to
        guarantee the singleton reflects the on-disk truth.
        """
        async with self._load_lock:
            self._loaded = False
            self._index = None
            self._chunks = []
            self._faiss = None
            logger.info("FaissStore: force_reload — in-memory state cleared.")

    async def clear_all(self) -> int:
        """Delete every chunk from the store and wipe the on-disk files.

        Returns:
            Number of chunks that were removed.
        """
        await self._ensure_loaded(None)

        count = len(self._chunks)
        if count == 0 and (self._index is None or self._index.ntotal == 0):
            logger.debug("clear_all: index already empty.")
            return 0

        if self._index is not None and self._faiss is not None:
            dimension = self._index.d
            self._index = self._faiss.IndexFlatIP(dimension)
        self._chunks = []

        self._persist_sync()
        logger.info("clear_all: removed %d chunk(s) — index now empty.", count)
        return count

    def get_source_ids(self) -> set[str]:
        """Return the set of unique source_ids currently in the store."""
        return {c.source_id for c in self._chunks if c.source_id}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _delete_by_source_id_sync(self, source_id: str) -> int:
        """Synchronous core of delete_by_source_id (runs in thread)."""
        indices_to_remove = [
            i for i, chunk in enumerate(self._chunks)
            if chunk.source_id == source_id
        ]

        if not indices_to_remove:
            logger.info(
                "delete_by_source_id: no chunks found for source_id=%s.", source_id
            )
            return 0

        remove_set = set(indices_to_remove)
        remaining_chunks = [
            chunk for i, chunk in enumerate(self._chunks) if i not in remove_set
        ]

        if not remaining_chunks:
            dimension = self._index.d
            self._index = self._faiss.IndexFlatIP(dimension)
            self._chunks = []
            logger.info(
                "delete_by_source_id: removed all %d chunk(s) — index now empty.",
                len(indices_to_remove),
            )
            self._persist_sync()
            return len(indices_to_remove)

        remaining_vectors = []
        remaining_indices = sorted(set(range(len(self._chunks))) - remove_set)
        for idx in remaining_indices:
            vec = self._index.reconstruct(int(idx))
            remaining_vectors.append(vec.tolist())

        arr = np.array(remaining_vectors, dtype=np.float32)
        self._index = self._faiss.IndexFlatIP(arr.shape[1])
        self._index.add(arr)
        self._chunks = remaining_chunks

        logger.info(
            "delete_by_source_id: removed %d chunk(s), index now has %d vectors.",
            len(indices_to_remove), self._index.ntotal,
        )
        self._persist_sync()
        return len(indices_to_remove)

    def _add_sync(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        arr = np.array(vectors, dtype=np.float32)
        arr = _normalize(arr)
        self._index.add(arr)
        self._chunks.extend(chunks)
        logger.debug("Added %d vectors; index total = %d.", len(vectors), self._index.ntotal)
        self._persist_sync()

    def _search_sync(
        self, query_vector: List[float], top_k: int) -> List[RetrievedChunk]:
        query = np.array([query_vector], dtype=np.float32)
        query = _normalize(query)
        scores, indices = self._index.search(query, top_k)

        results: List[RetrievedChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            results.append(RetrievedChunk(chunk=self._chunks[idx], score=float(score)))

        logger.debug("FAISS search returned %d result(s).", len(results))
        return results

    def _persist_sync(self) -> None:
        """Atomically write index + metadata to disk.

        Uses write-to-tempfile-then-rename so a crash during save never
        leaves a corrupt / half-written file on disk.
        """
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)

            # --- Write FAISS index to temp file, then rename ---
            tmp_fd, tmp_index_path = tempfile.mkstemp(
                dir=self._index_path.parent, suffix=".tmp"
            )
            try:
                os.close(tmp_fd)
                self._faiss.write_index(self._index, tmp_index_path)
                os.replace(tmp_index_path, str(self._index_path))
            except BaseException:
                _safe_unlink(tmp_index_path)
                raise

            # --- Write metadata JSON to temp file, then rename ---
            payload = [_chunk_to_dict(chunk) for chunk in self._chunks]
            json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            tmp_fd, tmp_meta_path = tempfile.mkstemp(
                dir=self._metadata_path.parent, suffix=".tmp"
            )
            try:
                os.write(tmp_fd, json_bytes)
                os.close(tmp_fd)
                os.replace(tmp_meta_path, str(self._metadata_path))
            except BaseException:
                _safe_unlink(tmp_meta_path)
                raise

            logger.debug(
                "Persisted FAISS index (%d vectors) to %s.",
                self._index.ntotal,
                self._index_path,
            )
        except OSError as exc:
            logger.error("Failed to persist FAISS index: %s", exc)
            raise

    async def _ensure_loaded(self, dimension: int | None) -> None:
        async with self._load_lock:
            if self._loaded:
                return
            await asyncio.to_thread(self._load_sync, dimension)
            self._loaded = True

    def _load_sync(self, dimension: int | None) -> None:
        try:
            import faiss
            self._faiss = faiss
        except ImportError as exc:
            raise RuntimeError(
                "faiss-cpu is not installed."
            ) from exc

        if self._index_path.exists():
            self._index = self._faiss.read_index(str(self._index_path))
            logger.debug(
                "Loaded FAISS index from %s (%d vectors).",
                self._index_path,
                self._index.ntotal,
            )
            if self._metadata_path.exists():
                try:
                    payload = json.loads(
                        self._metadata_path.read_text(encoding="utf-8")
                    )
                    self._chunks = [Chunk(**item) for item in payload]
                    logger.debug("Loaded %d chunk metadata entries.", len(self._chunks))
                except Exception as exc:
                    logger.error(
                        "Chunk metadata at %s is corrupt (%s) — metadata reset.",
                        self._metadata_path, exc,
                    )
                    self._chunks = []
            return

        if dimension is None:
            logger.debug("No existing index and no dimension — index deferred.")
            return

        self._index = self._faiss.IndexFlatIP(dimension)
        logger.debug("Created new FAISS IndexFlatIP (dimension=%d).", dimension)


# ------------------------------------------------------------------ #
# Module-level helpers
# ------------------------------------------------------------------ #

def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return vectors / norms


def _chunk_to_dict(chunk: Chunk) -> dict:
    if hasattr(chunk, "model_dump"):
        d = chunk.model_dump()
    elif hasattr(chunk, "_asdict"):
        d = chunk._asdict()
    else:
        try:
            from dataclasses import asdict
            d = asdict(chunk)
        except TypeError:
            d = dict(chunk.__dict__)
    # MappingProxyType is not JSON-serializable — convert to plain dict
    if "metadata" in d and hasattr(d["metadata"], "items"):
        d["metadata"] = dict(d["metadata"])
    return d


def _safe_unlink(path: str) -> None:
    """Best-effort file removal (for temp-file cleanup on failure)."""
    try:
        os.unlink(path)
    except OSError:
        pass
