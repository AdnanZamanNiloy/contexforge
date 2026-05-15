from __future__ import annotations

import asyncio
import logging
from typing import List

from app.config.settings import settings
from core.types import RerankedChunk, RetrievedChunk
from observability.tracer import observe

__all__ = ["Reranker"]

logger = logging.getLogger(__name__)


class Reranker:

    def __init__(self) -> None:
        self._model = None
        self._load_lock = asyncio.Lock()

    @observe(name="rerank")
    async def rerank(
        self,
        query: str,
        candidates: List[RetrievedChunk],
        top_k: int,) -> List[RerankedChunk]:

        if not isinstance(query, str) or not query.strip():
            raise ValueError("Reranker.rerank received an empty query")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        if not candidates:
            logger.debug("Reranker: no candidates — returning empty list.")
            return []

        await self._ensure_model_loaded()
        pairs = [(query, item.chunk.text) for item in candidates]
        raw_scores = await asyncio.to_thread(self._model.predict, pairs)

        scored = sorted(
            zip(candidates, (float(s) for s in raw_scores)),
            key=lambda pair: pair[1],
            reverse=True,
        )

        trimmed = scored[:top_k]

        results = [
            RerankedChunk(chunk=item.chunk, score=score, rank=rank)
            for rank, (item, score) in enumerate(trimmed, start=1)
        ]

        logger.debug(
            "Reranker: %d candidates → top %d selected; "
            "best=%.4f worst=%.4f",
            len(candidates),
            len(results),
            results[0].score if results else 0.0,
            results[-1].score if results else 0.0,
        )
        return results


    async def _ensure_model_loaded(self) -> None:
        async with self._load_lock:
            if self._model is not None:
                return
            await asyncio.to_thread(self._load_model_sync)

    def _load_model_sync(self) -> None:
     
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Reranker requires sentence-transformers. "
                "Run: pip install sentence-transformers"
            ) from exc

        logger.debug("Loading CrossEncoder model: %s", settings.RERANK_MODEL)
        self._model = CrossEncoder(settings.RERANK_MODEL)
        logger.debug("CrossEncoder model loaded successfully.")