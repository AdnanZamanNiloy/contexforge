"""Per-source inspection: what was actually extracted and indexed.

The workspace can list a source, rename it and delete it, but nothing let a
user confirm the extraction itself. That matters more than it sounds: a
scanned PDF yields no text, a DOCX loses its tables, and a bad fetch returns an
article's navigation instead of its body — and in every one of those cases the
source still appears in the sidebar and still answers questions. The gap between
"the file was uploaded" and "the right text was indexed" is invisible until you
can read what landed in the index.

This module assembles that view from data already stored: chunk metadata (title,
language, page counts, keywords, entities) and the chunk texts themselves.
Nothing here re-fetches or re-parses anything.
"""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Iterable
from typing import Any

from app.sources.schemas import SourceChunkOut, SourceContentResponse, SourceDetailResponse

__all__ = [
    "MAX_CONTENT_CHUNKS",
    "build_source_content",
    "build_source_detail",
]

logger = logging.getLogger(__name__)

# Enough to reconstruct a typical document without letting a 500-file repository
# push a multi-megabyte response. The `truncated` flag tells the client when this
# bites, so a partial view is never mistaken for the whole source.
MAX_CONTENT_CHUNKS = 200


def _loads(raw: Any, fallback: Any) -> Any:
    """Decode a JSON-ish metadata value, returning *fallback* on anything odd.

    Loader metadata is serialised with ``str()`` rather than stored as JSON, so
    these fields arrive as Python reprs ("['a', 'b']", "{'text': ...}"). They are
    best-effort enrichment for a read-only view, so a parse failure must degrade
    to empty rather than fail the request.
    """
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, (list, dict)):
        return raw
    try:
        value = json.loads(raw)
    except TypeError, ValueError:
        try:
            # literal_eval, not eval: the payload is loader-authored, but it is
            # still untrusted input and must never be executed as code.
            value = ast.literal_eval(raw)
        except TypeError, ValueError, SyntaxError:
            return fallback
    if isinstance(raw, str) and not isinstance(value, (list, dict)):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def _int_or_none(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except TypeError, ValueError:
        return None


def _bool_or_none(raw: Any) -> bool | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "1", "yes"}


def _chunk_sort_key(chunk: Any) -> tuple[str, int]:
    """Order chunks by file path, then by their recorded position.

    A repository indexes one document per file and every file restarts its chunk
    numbering at 0, so sorting on ``chunk_index`` alone would interleave
    unrelated files. Path first, position second.
    """
    meta = getattr(chunk, "metadata", None) or {}
    return (str(meta.get("path") or ""), _int_or_none(meta.get("chunk_index")) or 0)


def build_source_detail(
    chunks: Iterable[Any],
    *,
    source_id: str,
    derived_title: str,
    title_override: str | None = None,
) -> SourceDetailResponse:
    """Summarise one source's indexed chunks into a detail view.

    Args:
        chunks:        Every chunk belonging to the source.
        source_id:     The source being described.
        derived_title: Title from chunk metadata, before any user rename.
        title_override: The user's renamed title, if they set one.

    Returns:
        A populated :class:`SourceDetailResponse`.

    Field selection is deliberately first-wins rather than last-wins: loaders
    write these per chunk, so a value that disagrees between chunks of one
    document is a loader inconsistency, and taking the earliest chunk keeps the
    answer stable instead of dependent on iteration order.
    """
    ordered = sorted(chunks, key=_chunk_sort_key)
    first = ordered[0].metadata if ordered else {}

    source_type = str(first.get("source_type") or first.get("source") or "unknown")
    url = first.get("url") or None
    language = first.get("language") or None

    keywords: list[str] = []
    entities: list[dict] = []
    file_paths: list[str] = []
    seen_paths: set[str] = set()
    char_count = 0

    for chunk in ordered:
        meta = getattr(chunk, "metadata", None) or {}
        char_count += len(chunk.text)
        path = meta.get("path")
        if path and path not in seen_paths:
            seen_paths.add(str(path))
            file_paths.append(str(path))
        # Only the first chunk that actually carries a value supplies it.
        if not keywords:
            keywords = [str(k) for k in _loads(meta.get("keywords"), [])]
        if not entities:
            entities = [e for e in _loads(meta.get("named_entities"), []) if isinstance(e, dict)]

    display_title = title_override or derived_title

    return SourceDetailResponse(
        source_id=source_id,
        title=display_title,
        derived_title=derived_title,
        renamed=bool(title_override and title_override != derived_title),
        source_type=source_type,
        url=str(url) if url else None,
        chunk_count=len(ordered),
        char_count=char_count,
        language=str(language) if language else None,
        file_paths=sorted(file_paths),
        page_count=_int_or_none(first.get("page_count")),
        non_empty_pages=_int_or_none(first.get("non_empty_pages")),
        is_scanned=_bool_or_none(first.get("is_scanned")),
        keywords=keywords,
        named_entities=entities,
        file_available=False,
    )


def build_source_content(
    chunks: Iterable[Any],
    *,
    source_id: str,
    limit: int = MAX_CONTENT_CHUNKS,
) -> SourceContentResponse:
    """Return a source's indexed chunk text, capped at *limit* chunks."""
    ordered = sorted(chunks, key=_chunk_sort_key)
    shown = ordered[:limit] if limit > 0 else ordered

    out = [
        SourceChunkOut(
            chunk_id=chunk.chunk_id,
            chunk_index=_int_or_none((chunk.metadata or {}).get("chunk_index")),
            path=(chunk.metadata or {}).get("path") or None,
            text=chunk.text,
        )
        for chunk in shown
    ]

    logger.info(
        "build_source_content: source_id=%s returning %d of %d chunks",
        source_id,
        len(out),
        len(ordered),
    )

    return SourceContentResponse(
        source_id=source_id,
        chunks=out,
        chunk_count=len(out),
        total_chunks=len(ordered),
        truncated=len(out) < len(ordered),
    )
