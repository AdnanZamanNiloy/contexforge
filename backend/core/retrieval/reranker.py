from __future__ import annotations

import asyncio
import logging
import math
from typing import List, Tuple

from app.config.settings import settings
from core.types import RerankedChunk, RetrievedChunk
from observability.tracer import observe

__all__ = ["Reranker"]

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    """Logit → probability via the logistic function."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class Reranker:

    def __init__(self) -> None:
        self._model = None
        self._load_lock = asyncio.Lock()

    @observe(name="rerank")
    async def rerank(
        self,
        query: str,
        candidates: List[RetrievedChunk],
        top_k: int,
    ) -> Tuple[List[RerankedChunk], float]:
        """Rerank candidates with a cross-encoder, returning (chunks, mean_confidence).

        Each raw logit is normalised via sigmoid into a [0.0, 1.0] probability.
        The mean of the top‑k normalised scores is returned as the second element.

        Args:
            query:      User question used as the cross-encoder premise.
            candidates: RetrievedChunk list from hybrid retrieval.
            top_k:      Number of reranked chunks to keep.

        Returns:
            Tuple of (list of RerankedChunk, mean sigmoid confidence in [0.0, 1.0]).

        Raises:
            ValueError: If *query* is empty or *top_k* is not positive.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Reranker.rerank received an empty query")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        # FIX: guard for empty candidate list — return empty + zero confidence
        if not candidates:
            logger.debug("Reranker: no candidates — returning ([], 0.0).")
            return [], 0.0

        await self._ensure_model_loaded()

        pairs = [(query, item.chunk.text) for item in candidates]

        # FIX: raw logits from the cross-encoder (unbounded, typically -5 .. +5)
        raw_scores = await asyncio.to_thread(self._model.predict, pairs)

        # FIX: apply sigmoid to convert logits to probabilities
        probs = [_sigmoid(float(s)) for s in raw_scores]

        # Sort candidates by their sigmoid probability, descending
        scored = sorted(
            zip(candidates, probs),
            key=lambda pair: pair[1],
            reverse=True,
        )

        trimmed = scored[:top_k]

        results = [
            RerankedChunk(chunk=item.chunk, score=prob, rank=rank)
            for rank, (item, prob) in enumerate(trimmed, start=1)
        ]

        # FIX: mean confidence of the top-k only
        mean_confidence = (
            sum(prob for _, prob in trimmed) / len(trimmed)
            if trimmed
            else 0.0
        )

        logger.debug(
            "Reranker: %d candidates → top %d selected; "
            "best=%.4f worst=%.4f mean_conf=%.4f",
            len(candidates),
            len(results),
            results[0].score if results else 0.0,
            results[-1].score if results else 0.0,
            mean_confidence,
        )
        return results, mean_confidence


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
