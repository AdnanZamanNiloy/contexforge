from __future__ import annotations

from abc import ABC, abstractmethod

from core.types import RetrievedChunk

__all__ = ["Retriever"]


class Retriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        query_vector: list[float],
        top_k: int,
        exclude_source_ids: set[str] | None = None,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError
