from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Literal

__all__ = ["Embedder"]


class Embedder(ABC):

    @abstractmethod
    async def embed_texts(
        self,
        texts: List[str],
        input_type: Literal["document", "query"],
    ) -> List[List[float]]:
        raise NotImplementedError

    async def embed_single(
        self,
        text: str,
        input_type: Literal["document", "query"],
    ) -> List[float]:
     
        results = await self.embed_texts([text], input_type)
        return results[0]

    @abstractmethod
    async def aclose(self) -> None:
        raise NotImplementedError
       