from __future__ import annotations

from typing import List

from .base_loader import BaseLoader
from core.types import Document
from observability.tracer import observe


class TextLoader(BaseLoader):
    @observe(name="load_text")
    async def load(self, source: str | bytes, source_id: str) -> List[Document]:
        if isinstance(source, bytes):
            text = source.decode("utf-8", errors="ignore")
        else:
            text = source
        return [Document(document_id=source_id, text=text, metadata={"source_id": source_id}, source_type="text")]
