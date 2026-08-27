from __future__ import annotations

import logging

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
        query_vector: list[float],
        top_k: int,
        exclude_source_ids: set[str] | None = None,
    ) -> list[RetrievedChunk]:

        results = await self._store.search(query_vector, top_k, exclude_source_ids)
        logger.debug("DenseRetriever: returned %d result(s).", len(results))
        return results
