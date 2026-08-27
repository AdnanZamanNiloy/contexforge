from __future__ import annotations

import logging
from functools import lru_cache

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config.settings import settings
from core.types import Chunk, Document, validate_documents
from observability.tracer import observe

__all__ = ["TextChunker", "default_chunker", "get_token_len"]

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_encoder(encoding_name: str) -> tiktoken.Encoding:
    logger.debug("Loading tiktoken encoder: %s", encoding_name)
    return tiktoken.get_encoding(encoding_name)


def get_token_len(text: str) -> int:
    return len(_get_encoder("cl100k_base").encode(text))


_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]


class TextChunker:
    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self._chunk_size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE
        self._chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.CHUNK_OVERLAP

        if self._chunk_size <= 0:
            raise ValueError(f"chunk_size must be a positive integer, got {self._chunk_size}")
        if self._chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {self._chunk_overlap}")
        if self._chunk_overlap >= self._chunk_size:
            raise ValueError(
                f"chunk_overlap ({self._chunk_overlap}) must be strictly less than chunk_size ({self._chunk_size})"
            )

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            separators=_SEPARATORS,
            length_function=get_token_len,
            add_start_index=True,
            is_separator_regex=False,
        )
        logger.debug(
            "TextChunker initialised: chunk_size=%d, chunk_overlap=%d",
            self._chunk_size,
            self._chunk_overlap,
        )

    # Public API
    @observe(name="chunk_text")
    def chunk_documents(self, documents: list[Document]) -> list[Chunk]:

        validate_documents(documents, component="TextChunker")
        chunks: list[Chunk] = []
        for doc in documents:
            doc_chunks = self._chunk_document(doc)
            chunks.extend(doc_chunks)
            logger.debug("Document '%s' split into %d chunk(s).", doc.document_id, len(doc_chunks))
        logger.debug("TextChunker produced %d total chunk(s).", len(chunks))
        return chunks

    def _chunk_document(self, doc: Document) -> list[Chunk]:
        """Return all chunks for a single document."""
        chunks: list[Chunk] = []
        for index, text in enumerate(self._split_text(doc.text)):
            metadata = dict(doc.metadata)
            metadata["chunk_index"] = index
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.document_id}:{index}",
                    text=text,
                    metadata=metadata,
                    # Prefer metadata["source_id"] (the source UUID) so
                    # sources whose document_id differs (e.g. GitHub files named
                    # "{uuid}:path") can be deleted by source_id.  All loaders set
                    # metadata["source_id"] = the ingestion source UUID.
                    source_id=metadata.get("source_id") or doc.document_id,
                )
            )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        """Split *text*, filtering out whitespace-only fragments."""
        if not text.strip():
            return []
        return [chunk for chunk in self._splitter.split_text(text) if chunk.strip()]


default_chunker = TextChunker()
