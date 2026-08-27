from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections import Counter

from core.types import Document, validate_documents

__all__ = ["TextCleaner"]

logger = logging.getLogger(__name__)


class TextCleaner:
    _URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
    _EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}\b")
    _PAGE_RE = re.compile(r"^\s*(page|p\.?)[\s:]*\d+(\s*of\s*\d+)?\s*$", re.IGNORECASE)
    _LIST_RE = re.compile(r"^\s*([-*+]|\d+[\.)])\s+\S+")
    _SEPARATOR_RE = re.compile(r"^\s*[-=_*~]{3,}\s*$")

    _PUNCT_RE = re.compile(r"[^\w\s]{5,}")

    _BOILERPLATE_MIN_LEN = 6
    _BOILERPLATE_MAX_LEN = 80

    def __init__(self, max_blank_lines: int = 2) -> None:
        self._max_blank_lines = max(1, max_blank_lines)

    async def clean(self, documents: list[Document]) -> list[Document]:
        return await asyncio.to_thread(self._clean_sync, documents)

    def _clean_sync(self, documents: list[Document]) -> list[Document]:
        validate_documents(documents, component="TextCleaner")
        cleaned: list[Document] = []
        for doc in documents:
            cleaned_text = self._clean_text(doc.text)
            if not cleaned_text.strip():
                raise ValueError(
                    f"TextCleaner produced empty text for document '{doc.document_id}'. "
                    "The original text may consist entirely of boilerplate, page numbers, "
                    "or separator lines."
                )
            cleaned.append(
                Document(
                    document_id=doc.document_id,
                    text=cleaned_text,
                    metadata=dict(doc.metadata),
                    source_type=doc.source_type,
                )
            )
        return cleaned

    def _clean_text(self, text: str) -> str:

        text = unicodedata.normalize("NFC", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = self._URL_RE.sub(" ", text)
        text = self._EMAIL_RE.sub(" ", text)
        lines = text.split("\n")
        normalized_lines = [self._normalize_line(line) for line in lines]

        counts: Counter[str] = Counter(
            line
            for line in normalized_lines
            if (self._BOILERPLATE_MIN_LEN <= len(line) <= self._BOILERPLATE_MAX_LEN and not self._is_list_line(line))
        )
        boilerplate = {line for line, count in counts.items() if count >= 2}
        if boilerplate:
            logger.debug(
                "Detected %d boilerplate pattern(s): %s",
                len(boilerplate),
                list(boilerplate)[:5],
            )

        cleaned_lines: list[str] = []
        for original, normalized in zip(lines, normalized_lines, strict=False):
            if not normalized:
                cleaned_lines.append("")
                continue

            if self._PAGE_RE.match(normalized) or normalized.isdigit():
                logger.debug("Removed page-number line: %r", normalized)
                continue

            if self._SEPARATOR_RE.match(normalized):
                logger.debug("Removed separator line: %r", normalized)
                continue

            if normalized in boilerplate:
                logger.debug("Removed boilerplate line: %r", normalized)
                continue

            if self._is_list_line(original):
                cleaned_lines.append(self._normalize_list_line(original))
            else:
                cleaned_lines.append(normalized)

        cleaned_text = "\n".join(cleaned_lines).strip()
        cleaned_text = self._PUNCT_RE.sub(" ", cleaned_text)

        blank_line_re = re.compile(rf"\n{{{self._max_blank_lines + 1},}}")
        cleaned_text = blank_line_re.sub("\n" * self._max_blank_lines, cleaned_text)

        cleaned_text = re.sub(r"[ \t]{2,}", " ", cleaned_text)
        return cleaned_text

    @staticmethod
    def _normalize_line(line: str) -> str:
        return re.sub(r"\s+", " ", line.strip())

    def _normalize_list_line(self, line: str) -> str:
        match = re.match(r"^(\s*)([-*+]|\d+[\.)])\s+(.*)$", line)
        if not match:
            return self._normalize_line(line)
        indent, bullet, rest = match.groups()
        rest = re.sub(r"\s+", " ", rest.strip())
        return f"{indent}{bullet} {rest}"

    def _is_list_line(self, line: str) -> bool:
        return bool(self._LIST_RE.match(line))
