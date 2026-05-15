from __future__ import annotations

import asyncio
import logging
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

   
    # Public API

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
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            self._faiss.write_index(self._index, str(self._index_path))
            payload = [_chunk_to_dict(chunk) for chunk in self._chunks]
            self._metadata_path.write_text(
            
                __import__("json").dumps(payload, separators=(",", ":")),
                encoding="utf-8",
            )
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
                    import json
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



def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return vectors / norms


def _chunk_to_dict(chunk: Chunk) -> dict:
   
    if hasattr(chunk, "model_dump"):         
        return chunk.model_dump()
    if hasattr(chunk, "_asdict"):            
        return chunk._asdict()
    try:
        from dataclasses import asdict       
        return asdict(chunk)
    except TypeError:
        return chunk.__dict__                 