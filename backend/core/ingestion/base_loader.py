from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.types import Document


class BaseLoader(ABC):
    """Base loader for ingestion sources."""

    @abstractmethod
    async def load(
        self,
        source: str | bytes,
        source_id: str,
        filename: Optional[str] = None,
    ) -> List[Document]:
        raise NotImplementedError
