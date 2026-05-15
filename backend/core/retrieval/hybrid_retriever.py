from __future__ import annotations

import asyncio
import logging
from typing import List

from core.retrieval.bm25_retriever import BM25Retriever
from core.retrieval.dense_retriever import DenseRetriever
from core.retrieval.rrf_fusion import RRFFusion
from core.types import RetrievedChunk
from observability.tracer import observe

__all__ = ["HybridRetriever"]

logger = logging.getLogger(__name__)


class HybridRetriever:

    def __init__(
        self,
        bm25: BM25Retriever,
        dense: DenseRetriever,
        fusion: RRFFusion | None = None,) -> None:
        self._bm25 = bm25
        self._dense = dense
        self._fusion = fusion or RRFFusion()

    @observe(name="hybrid_retrieve")
    async def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,) -> List[RetrievedChunk]:

        if not isinstance(query, str) or not query.strip():
            raise ValueError("HybridRetriever.retrieve received an empty query")
        if not query_vector:
            raise ValueError("HybridRetriever.retrieve received an empty query_vector")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        
        bm25_result, dense_result = await asyncio.gather(
            self._bm25.retrieve(query, query_vector, top_k),
            self._dense.retrieve(query, query_vector, top_k),
            return_exceptions=True,
        )

        # Degrade gracefully when one leg fails
        bm25_chunks = self._unwrap(bm25_result, leg="BM25")
        dense_chunks = self._unwrap(dense_result, leg="Dense")

        if not bm25_chunks and not dense_chunks:
            logger.error(
                "HybridRetriever: both retrieval legs failed for query %r.", query
            )
            return []

        fused = self._fusion.fuse(bm25_chunks, dense_chunks)
        results = fused[:top_k]

        logger.debug(
            "HybridRetriever: bm25=%d dense=%d fused=%d returned=%d",
            len(bm25_chunks), len(dense_chunks), len(fused), len(results),
        )
        return results


    @staticmethod
    def _unwrap(
        result: List[RetrievedChunk] | BaseException,leg: str,) -> List[RetrievedChunk]:
      
        if isinstance(result, BaseException):
            logger.warning(
                "HybridRetriever: %s retrieval leg failed (%s: %s) — "
                "continuing with empty results for this leg.",
                leg, type(result).__name__, result,
            )
            return []
        return result