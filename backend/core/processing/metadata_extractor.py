from __future__ import annotations

import asyncio
import copy
import logging
import re
from collections import Counter
from typing import Dict, List, Optional

from core.types import Document

__all__ = ["MetadataExtractor"]

logger = logging.getLogger(__name__)

# Maximum characters passed to spaCy to avoid memory spikes on large documents.
_SPACY_MAX_CHARS = 50_000


def _validate_documents(documents: List[Document]) -> None:
    if not isinstance(documents, list):
        raise ValueError(
            f"MetadataExtractor expected a list of Document objects, got {type(documents).__name__}"
        )
    if not documents:
        raise ValueError("MetadataExtractor received an empty document list")
    for idx, doc in enumerate(documents):
        if not isinstance(doc, Document):
            raise ValueError(
                f"MetadataExtractor expected Document at index {idx}, got {type(doc).__name__}"
            )
        if not isinstance(doc.text, str) or not doc.text.strip():
            raise ValueError(
                f"MetadataExtractor received empty text for document '{doc.document_id}'"
            )


class MetadataExtractor:

    _WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{2,}")
    _STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "has", "have", "he", "her", "his", "i", "in", "is", "it",
        "its", "of", "on", "or", "our", "she", "that", "the", "their",
        "they", "this", "to", "was", "were", "with", "you", "your",
    }

    def __init__(self, top_n_keywords: int = 10) -> None:
        self._top_n_keywords = max(1, top_n_keywords)
        self._nlp: Optional[object] = None
        self._nlp_loaded = False

   

    async def extract(self, documents: List[Document]) -> List[Document]:
        return await asyncio.to_thread(self._extract_sync, documents)


    def _extract_sync(self, documents: List[Document]) -> List[Document]:
        _validate_documents(documents)
        self._ensure_nlp_loaded()

        enriched: List[Document] = []
        for doc in documents:
            title = self._extract_title(doc.text)
            keywords = self._extract_keywords(doc.text)
            named_entities = self._extract_entities(doc.text)

            metadata: Dict[str, object] = copy.deepcopy(doc.metadata)
            metadata.update(
                {
                    "title": title,
                    "char_count": len(doc.text),
                    "source": doc.source_type or "unknown",
                    "named_entities": named_entities,
                    "keywords": keywords,
                }
            )
            enriched.append(
                Document(
                    document_id=doc.document_id,
                    text=doc.text,
                    metadata=metadata,
                    source_type=doc.source_type,
                )
            )
        return enriched

    def _ensure_nlp_loaded(self) -> None:
        if self._nlp_loaded:
            return
        self._nlp_loaded = True
        try:
            import spacy
            self._nlp = spacy.load("en_core_web_sm")
            logger.debug("spaCy model 'en_core_web_sm' loaded successfully.")
        except Exception as exc:
            logger.warning(
                "spaCy unavailable (%s); falling back to regex entity extraction.", exc
            )
            self._nlp = None


    def _extract_title(self, text: str) -> str:
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
            return stripped
        return "untitled"



    def _extract_keywords(self, text: str) -> List[str]:
        tokens = [t.lower() for t in self._WORD_RE.findall(text)]
        filtered = [t for t in tokens if t not in self._STOPWORDS]
        if not filtered:
            return []
        return [word for word, _ in Counter(filtered).most_common(self._top_n_keywords)]



    def _extract_entities(self, text: str) -> List[Dict[str, str]]:
        if self._nlp is not None:
            doc = self._nlp(text[:_SPACY_MAX_CHARS])
            seen: set = set()
            entities: List[Dict[str, str]] = []
            for ent in doc.ents:
                key = (ent.text, ent.label_)
                if key in seen:
                    continue
                seen.add(key)
                entities.append({"text": ent.text, "label": ent.label_})
            return entities

        matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text)
        seen = set()
        entities = []
        for match in matches:
            if match in seen:
                continue
            seen.add(match)
            entities.append({"text": match, "label": "REGEX"})
        return entities