from __future__ import annotations

from core.types import Document
from observability.tracer import observe

from .base_loader import BaseLoader


class TextLoader(BaseLoader):
    @observe(name="load_text")
    async def load(
        self,
        source: str | bytes,
        source_id: str,
        filename: str | None = None,
        metadata: dict | None = None,
    ) -> list[Document]:
        text = source.decode("utf-8", errors="ignore") if isinstance(source, bytes) else source
        return [Document(document_id=source_id, text=text, metadata={"source_id": source_id}, source_type="text")]
