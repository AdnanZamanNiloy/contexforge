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
        # Fallback: older code may have written metadata to .meta.json
        self._metadata_path_alt: Path = self._index_path.parent / (
            self._index_path.stem + ".meta.json"
        )

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
    async def search(self, query_vector: List[float], top_k: int, exclude_source_ids: set[str] | None = None) -> List[RetrievedChunk]:
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

        return await asyncio.to_thread(
            self._search_sync, query_vector, effective_top_k, exclude_source_ids
        )

    @observe(name="faiss_delete_by_source")
    async def delete_by_source_id(self, source_id: str) -> int:
        """Remove all chunks belonging to *source_id* from the FAISS index.

        Holds the load lock for the entire delete-persist-reload cycle to
        prevent concurrent searches from reading stale in-memory state.

        FAISS IndexFlatIP does not support native deletion, so this method
        rebuilds the index from scratch with a **fresh** IndexFlatIP
        (not reusing the old object) to avoid accumulated internal state.

        Returns:
            Number of chunks removed.
        """
        if not source_id:
            raise ValueError("source_id must not be empty")

        async with self._load_lock:
            if not self._loaded:
                await asyncio.to_thread(self._load_sync, None)
                self._loaded = True

            if self._index is None or not self._chunks:
                logger.debug("delete_by_source_id: index empty — nothing to delete.")
                return 0

            removed = await asyncio.to_thread(
                self._delete_by_source_id_sync, source_id
            )

            # Force reload from the freshly-persisted disk state so in-memory
            # is guaranteed to reflect the on-disk truth.  This also clears
            # any stale FAISS internal state.
            self._loaded = False
            self._index = None
            self._chunks = []
            self._faiss = None
            await asyncio.to_thread(self._load_sync, None)
            self._loaded = True

            logger.info(
                "delete_by_source_id: completed source_id=%s removed=%d "
                "remaining=%d vectors.",
                source_id, removed, self._index.ntotal if self._index else 0,
            )
            return removed

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

        # Delete on-disk files so nothing persists across restarts
        _safe_unlink(str(self._index_path))
        _safe_unlink(str(self._metadata_path))
        _safe_unlink(str(self._metadata_path_alt))

        logger.info("clear_all: removed %d chunk(s) — index now empty, files deleted.", count)
        return count

    def get_source_ids(self) -> set[str]:
        """Return the set of unique source_ids currently in the store."""
        return {c.source_id for c in self._chunks if c.source_id}

    async def get_source_info(self) -> list[dict]:
        """Return grouped source info with metadata from stored chunks.

        Groups chunks by source_id and returns one entry per source with
        title, type, chunk count, and representative metadata.
        If _chunks is empty but FAISS has vectors, attempts a disk reload.
        """
        await self._ensure_loaded(None)

        # If chunks are empty but index has vectors, metadata file was
        # likely missing/corrupt on first load — try reloading now.
        if not self._chunks and self._index is not None and self._index.ntotal > 0:
            logger.warning(
                "get_source_info: %d vectors in FAISS but 0 chunks in memory — "
                "attempting disk reload.", self._index.ntotal,
            )
            async with self._load_lock:
                self._loaded = False
                self._chunks = []
                await asyncio.to_thread(self._load_sync, None)
                self._loaded = True
            logger.info(
                "get_source_info: after reload — %d chunks in memory.",
                len(self._chunks),
            )

        groups: dict[str, dict] = {}
        for chunk in self._chunks:
            sid = chunk.source_id or "unknown"
            if sid not in groups:
                meta = dict(chunk.metadata) if chunk.metadata else {}
                groups[sid] = {
                    "source_id": sid,
                    "title": meta.get("title") or meta.get("filename") or sid[:12],
                    "type": meta.get("source_type", "unknown"),
                    "url": meta.get("url", ""),
                    "chunks": 0,
                }
            groups[sid]["chunks"] += 1
        return list(groups.values())

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _delete_by_source_id_sync(self, source_id: str) -> int:
        """Synchronous core of delete_by_source_id (runs in thread).

        Creates a **brand-new** IndexFlatIP rather than reusing the old
        object, to avoid any accumulated internal FAISS state after
        repeated delete/rebuild cycles.
        """
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

        dimension = self._index.d

        if not remaining_chunks:
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

        # Always create a fresh index — never reuse the old object.
        self._index = self._faiss.IndexFlatIP(dimension)
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
        self, query_vector: List[float], top_k: int,
        exclude_source_ids: set[str] | None = None,
    ) -> List[RetrievedChunk]:
        query = np.array([query_vector], dtype=np.float32)
        query = _normalize(query)

        # Over-fetch to account for defensive filtering
        fetch_k = top_k * 3 if exclude_source_ids else top_k
        fetch_k = min(fetch_k, self._index.ntotal)
        scores, indices = self._index.search(query, fetch_k)

        results: List[RetrievedChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            chunk = self._chunks[idx]
            # Defensive filtering: skip chunks from deleted sources
            if exclude_source_ids and chunk.source_id in exclude_source_ids:
                logger.debug(
                    "FAISS search: filtered out chunk %s (source_id=%s in exclude set).",
                    chunk.chunk_id, chunk.source_id,
                )
                continue
            results.append(RetrievedChunk(chunk=chunk, score=float(score)))
            if len(results) >= top_k:
                break

        logger.debug("FAISS search returned %d result(s) (excluded %d).",
                      len(results),
                      sum(1 for score, idx in zip(scores[0], indices[0])
                          if idx >= 0 and idx < len(self._chunks)
                          and exclude_source_ids
                          and self._chunks[idx].source_id in exclude_source_ids))
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
                # Remove stale alt metadata file if it exists
                _safe_unlink(str(self._metadata_path_alt))
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
            if self._loaded and self._index is not None:
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
            # Try primary metadata path, then alt (.meta.json)
            metadata_path = None
            if self._metadata_path.exists():
                metadata_path = self._metadata_path
            elif self._metadata_path_alt.exists():
                metadata_path = self._metadata_path_alt
                logger.info(
                    "Using alternate metadata file %s", metadata_path
                )

            if metadata_path is not None:
                try:
                    payload = json.loads(
                        metadata_path.read_text(encoding="utf-8")
                    )
                    if payload:
                        self._chunks = [Chunk(**item) for item in payload]
                        logger.debug("Loaded %d chunk metadata entries.", len(self._chunks))
                    else:
                        logger.warning("Metadata file %s is empty.", metadata_path)
                        self._chunks = []
                except Exception as exc:
                    logger.error(
                        "Chunk metadata at %s is corrupt (%s) — metadata reset.",
                        metadata_path, exc,
                    )
                    self._chunks = []
            else:
                logger.warning(
                    "FAISS index loaded (%d vectors) but no metadata file found "
                    "(checked %s and %s).",
                    self._index.ntotal, self._metadata_path, self._metadata_path_alt,
                )
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
