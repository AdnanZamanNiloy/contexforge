from __future__ import annotations

import logging
from typing import List

from core.interfaces.retriever import Retriever
from core.storage.faiss_store import FaissStore
from core.types import RetrievedChunk
from observability.tracer import observe

__all__ = ["DenseRetriever"]

logger = logging.getLogger(__name__)


class DenseRetriever(Retriever):

    def __init__(self, store: FaissStore) -> None:
        self._store = store

    @observe(name="dense_retrieve")
    async def retrieve(
        self,
        query: str,  
        query_vector: List[float],
        top_k: int,
    ) -> List[RetrievedChunk]:
       
        results = await self._store.search(query_vector, top_k)
        logger.debug("DenseRetriever: returned %d result(s).", len(results))
        return results