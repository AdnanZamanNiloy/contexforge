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

# Per-source coverage guarantee.  When a question is answered over several
# loaded sources, the pure relevance-sorted top-k tends to be flooded by the
# single most similar source, so the answer silently ignores the others.  We
# reserve a slot for every distinct source present in the candidates (up to
# ``_MAX_CHUNKS_PER_SOURCE`` per source) so multi-source questions actually
# get grounded in all of them.
_MAX_CHUNKS_PER_SOURCE = 4


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


def _diversify(
    scored: List[Tuple[RetrievedChunk, float]],
    top_k: int,
) -> List[Tuple[RetrievedChunk, float]]:
    """Select up to ``top_k`` chunks while keeping per-source coverage.

    A purely relevance-sorted top-k lets the single most similar source crowd
    out every other loaded source, so a question spanning 3-4+ sources gets
    answered from only one of them.  This spreads the slots across sources:

    1. Every distinct source is guaranteed at least one chunk (its current
       best), so nothing is silently dropped.
    2. Remaining slots (up to ``_MAX_CHUNKS_PER_SOURCE`` per source) are filled
       greedily: at each step we take the highest-scoring *available* chunk of
       whichever source currently offers the strongest next candidate.

    Chunks with no ``source_id`` are grouped as one anonymous source so they
    still get a fair share.  If there is only a single source, the relevance
    order is preserved unchanged.

    Args:
        scored:    Candidate ``(RetrievedChunk, prob)`` pairs, sorted best-first.
        top_k:     Maximum number of chunks to return.

    Returns:
        Up to ``top_k`` pairs, ranked best-first.
    """
    if not scored or top_k <= 0:
        return scored[:top_k]

    # Only one source (or everything fits): relevance order is the answer.
    distinct_sources = {item[0].chunk.source_id or "__anonymous__" for item in scored}
    if len(distinct_sources) <= 1 or len(scored) <= top_k:
        return scored[:top_k]

    # Group each source's candidates, best-first within each group.
    by_source: Dict[str, List[Tuple[RetrievedChunk, float]]] = {}
    for item in scored:
        sid = item[0].chunk.source_id or "__anonymous__"
        by_source.setdefault(sid, []).append(item)

    # Order sources by their strongest candidate so seeding respects relevance.
    source_order = sorted(
        by_source,
        key=lambda sid: by_source[sid][0][1],
        reverse=True,
    )

    # Round 1: seed one slot per source (its best chunk).  This guarantees every
    # source present in the candidates is represented in the final selection.
    chosen: List[Tuple[RetrievedChunk, float]] = []
    for sid in source_order:
        chosen.append(by_source[sid][0])
        if len(chosen) >= top_k:
            return chosen

    # Round 2: fill remaining slots greedily by relevance, honouring the cap.
    cursors: Dict[str, int] = {sid: 1 for sid in by_source}
    while len(chosen) < top_k:
        best_sid = None
        best_score = None
        for sid, data in by_source.items():
            idx = cursors[sid]
            if idx >= len(data) or idx >= _MAX_CHUNKS_PER_SOURCE:
                continue
            if best_score is None or data[idx][1] > best_score:
                best_score = data[idx][1]
                best_sid = sid
        if best_sid is None:
            break
        chosen.append(by_source[best_sid][cursors[best_sid]])
        cursors[best_sid] += 1

    # Return best-first so downstream rank assignment (1 = strongest) is correct.
    chosen.sort(key=lambda pair: pair[1], reverse=True)
    return chosen


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
        """Rerank candidates with a cross-encoder, returning (chunks, confidence).

        Each raw logit is calibrated via temperature-scaled sigmoid into a
        [0.0, 1.0] probability.  The confidence value is the *best* calibrated
        score among the top-k results (not the mean), because the answer is
        grounded in the strongest source — a tail of tangential chunks should
        not dilute it.  It is floored at ``_MIN_CONFIDENCE_FLOOR`` when there
        are valid results.

        Args:
            query:      User question used as the cross-encoder premise.
            candidates: RetrievedChunk list from hybrid retrieval.
            top_k:      Number of reranked chunks to keep.

        Returns:
            Tuple of (list of RerankedChunk, confidence in [0.0, 1.0]).

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

        trimmed = _diversify(scored, top_k)

        results = [
            RerankedChunk(chunk=item.chunk, score=prob, rank=rank)
            for rank, (item, prob) in enumerate(trimmed, start=1)
        ]

        # Confidence = best calibrated score among the top-k results, with a
        # floor to avoid 0% on valid results.  Using the best source rather
        # than the mean stops tangential chunks from diluting a strong match.
        raw_best = (
            max(prob for _, prob in trimmed)
            if trimmed
            else 0.0
        )
        confidence = max(raw_best, _MIN_CONFIDENCE_FLOOR) if trimmed else 0.0

        logger.debug(
            "Reranker: %d candidates → top %d selected; "
            "best=%.4f worst=%.4f conf=%.4f",
            len(candidates),
            len(results),
            results[0].score if results else 0.0,
            results[-1].score if results else 0.0,
            confidence,
        )
        return results, confidence

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
