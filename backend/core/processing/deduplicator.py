from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import unicodedata

from core.types import Document

__all__ = ["Deduplicator"]

logger = logging.getLogger(__name__)


def _validate_documents(documents: list[Document]) -> None:

    if not isinstance(documents, list):
        raise TypeError(f"Deduplicator expected a list of Document objects, got {type(documents).__name__}")
    if not documents:
        raise ValueError("Deduplicator received an empty document list")
    for idx, doc in enumerate(documents):
        if not isinstance(doc, Document):
            raise TypeError(f"Deduplicator expected Document at index {idx}, got {type(doc).__name__}")
        if not isinstance(doc.text, str) or not doc.text.strip():
            raise ValueError(f"Deduplicator received empty or non-string text for document '{doc.document_id}'")


class Deduplicator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen_hashes: set[str] = set()

    async def deduplicate(self, documents: list[Document]) -> list[Document]:
        return await asyncio.to_thread(self._deduplicate_sync, documents)

    def reset(self) -> None:
        with self._lock:
            self._seen_hashes.clear()
        logger.debug("Deduplicator state reset; seen-hash set cleared.")

    def _deduplicate_sync(self, documents: list[Document]) -> list[Document]:

        _validate_documents(documents)
        unique: list[Document] = []

        for doc in documents:
            digest = self._fingerprint(doc.text, doc.metadata.get("source_id"))
            with self._lock:
                is_duplicate = digest in self._seen_hashes
                if not is_duplicate:
                    self._seen_hashes.add(digest)

            if is_duplicate:
                logger.debug("Duplicate document skipped: %s", doc.document_id)
                continue

            unique.append(doc)

        logger.debug(
            "Deduplication complete: %d in, %d unique, %d skipped.",
            len(documents),
            len(unique),
            len(documents) - len(unique),
        )
        return unique

    @staticmethod
    def _fingerprint(text: str, source_id: str | None = None) -> str:
        # Scope by source: identical text from *different* sources must still be
        # indexed (e.g. the same file ingested under a loose UUID source vs. a
        # repo-scoped `repo:owner/name` source). Only repeat content within the
        # same source is treated as a duplicate.
        parts = [source_id or "", text]
        normalised = unicodedata.normalize("NFC", "\x1f".join(parts))
        return hashlib.blake2b(normalised.encode("utf-8"), digest_size=32).hexdigest()
