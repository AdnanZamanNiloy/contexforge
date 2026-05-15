from __future__ import annotations

import logging
from typing import Dict, List

from core.types import RetrievedChunk

__all__ = ["RRFFusion"]

logger = logging.getLogger(__name__)


class RRFFusion:
  
    def __init__(self, k: int = 60) -> None:
        if k <= 0:
            raise ValueError(f"RRFFusion k must be a positive integer, got {k}")
        self._k = k

    def fuse(
        self,
        bm25_results: List[RetrievedChunk],
        dense_results: List[RetrievedChunk],) -> List[RetrievedChunk]:
     
        if not bm25_results and not dense_results:
            logger.warning("RRFFusion.fuse received two empty result lists.")
            return []

        scores: Dict[str, float] = {}

        chunk_map: Dict[str, RetrievedChunk] = {}

        for rank, result in enumerate(bm25_results, start=1):
            cid = result.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (self._k + rank)
            chunk_map.setdefault(cid, result)  

        for rank, result in enumerate(dense_results, start=1):
            cid = result.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (self._k + rank)
            chunk_map.setdefault(cid, result)   

        fused = [
            RetrievedChunk(chunk=chunk_map[cid].chunk, score=score)
            for cid, score in scores.items()
        ]
        fused.sort(key=lambda item: item.score, reverse=True)

        logger.debug(
            "RRFFusion: bm25=%d dense=%d unique=%d fused=%d",
            len(bm25_results),
            len(dense_results),
            len(fused),
            len(fused),
        )
        return fused