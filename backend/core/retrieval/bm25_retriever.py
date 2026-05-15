from __future__ import annotations

import logging
from typing import List

from core.interfaces.retriever import Retriever
from core.storage.bm25_index import BM25Index
from core.types import RetrievedChunk
from observability.tracer import observe

__all__ = ["BM25Retriever"]

logger = logging.getLogger(__name__)


class BM25Retriever(Retriever):

    def __init__(self, index: BM25Index) -> None:
        self._index = index

    @observe(name="bm25_retrieve")
    async def retrieve(
        self,
        query: str,
        query_vector: List[float],  
        top_k: int,
    ) -> List[RetrievedChunk]:

        results = await self._index.search(query, top_k)
        logger.debug("BM25Retriever: query=%r returned %d result(s).", query, len(results))
        return results