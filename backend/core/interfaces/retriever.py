
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from core.types import RetrievedChunk

__all__ = ["Retriever"]


class Retriever(ABC):
 

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
    ) -> List[RetrievedChunk]:
        raise NotImplementedError
