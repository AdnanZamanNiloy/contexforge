from __future__ import annotations

import asyncio
import logging
from typing import List

from .base_loader import BaseLoader
from core.types import Document
from observability.tracer import observe

logger = logging.getLogger(__name__)


class PDFLoader(BaseLoader):

    @observe(name="load_pdf")
    async def load(self, source: str | bytes, source_id: str) -> List[Document]:
        text, metadata = await asyncio.to_thread(self._extract_text, source) 
        metadata.update({"source_id": source_id, "source_type": "pdf"})       
        return [
            Document(
                document_id=source_id,
                text=text,
                metadata=metadata,
                source_type="pdf",
            )
        ]

    def _extract_text(self, source: str | bytes) -> tuple[str, dict]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:                         
            logger.exception("pypdf not installed")
            raise RuntimeError("PDF loader requires pypdf") from exc

        if isinstance(source, bytes):
            from io import BytesIO
            reader = PdfReader(BytesIO(source))
        else:
            reader = PdfReader(source)

        pages = [page.extract_text() or "" for page in reader.pages]
        page_count = len(pages)
        non_empty = sum(1 for p in pages if p.strip())

        
        if non_empty == 0:
            logger.warning(
                "PDF appears to be scanned/image-based (no extractable text). "
                "source_id=%s, pages=%d",
                None,
                page_count,
            )

        text = "\n\n".join(pages)

        metadata = {
            "page_count": page_count,                      
            "non_empty_pages": non_empty,
            "is_scanned": non_empty == 0,
        }

        return text, metadata