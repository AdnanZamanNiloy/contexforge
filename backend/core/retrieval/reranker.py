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

# Calibration constants for ms-marco-MiniLM-L-6-v2.
# Temperature > 1 softens the distribution (less extreme sigmoid values).
# Shift moves the operating point right so mediocre logits still produce
# reasonable confidence.
_CALIBRATION_TEMPERATURE = 2.0
_CALIBRATION_SHIFT = 2.0

# Absolute floor: even when reranker scores are mediocre, if we have valid
# results, confidence never drops below this (avoids the "always 0%" problem).
_MIN_CONFIDENCE_FLOOR = 0.15


def _sigmoid(x: float) -> float:
    """Logit → probability via the logistic function."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _calibrate(raw_logit: float) -> float:
    """Map a raw cross-encoder logit to a well-calibrated [0, 1] score.

    Applies temperature scaling and a positive shift so that:
      - Raw logit  0  → ~0.73  (mediocre match)
      - Raw logit  2  → ~0.88  (good match)
      - Raw logit  4  → ~0.95  (strong match)
      - Raw logit -2  → ~0.50  (weak but non-zero)
      - Raw logit -4  → ~0.27  (poor)
    """
    calibrated = (raw_logit + _CALIBRATION_SHIFT) / _CALIBRATION_TEMPERATURE
    return _sigmoid(calibrated)


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

        Each raw logit is calibrated via temperature-scaled sigmoid into a
        [0.0, 1.0] probability.  The mean of the top-k calibrated scores is
        returned as the confidence value, floored at ``_MIN_CONFIDENCE_FLOOR``
        when there are valid results.

        Args:
            query:      User question used as the cross-encoder premise.
            candidates: RetrievedChunk list from hybrid retrieval.
            top_k:      Number of reranked chunks to keep.

        Returns:
            Tuple of (list of RerankedChunk, mean confidence in [0.0, 1.0]).

        Raises:
            ValueError: If *query* is empty or *top_k* is not positive.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Reranker.rerank received an empty query")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        if not candidates:
            logger.debug("Reranker: no candidates — returning ([], 0.0).")
            return [], 0.0

        await self._ensure_model_loaded()

        pairs = [(query, item.chunk.text) for item in candidates]

        raw_scores = await asyncio.to_thread(self._model.predict, pairs)

        # Apply calibrated sigmoid (temperature-scaled + shifted)
        probs = [_calibrate(float(s)) for s in raw_scores]

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

        # Mean confidence of top-k, with floor to avoid 0% on valid results
        raw_mean = (
            sum(prob for _, prob in trimmed) / len(trimmed)
            if trimmed
            else 0.0
        )
        mean_confidence = max(raw_mean, _MIN_CONFIDENCE_FLOOR) if trimmed else 0.0

        logger.debug(
            "Reranker: %d candidates → top %d selected; "
            "best=%.4f worst=%.4f raw_mean=%.4f mean_conf=%.4f",
            len(candidates),
            len(results),
            results[0].score if results else 0.0,
            results[-1].score if results else 0.0,
            raw_mean,
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
