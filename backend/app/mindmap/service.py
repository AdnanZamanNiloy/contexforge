"""Application service for Mind Map generation.

Layered:  route -> service -> (LLM + FaissStore) + MindMapStore.

The service gathers a source's chunks from the vector store, asks the LLM to
condense them into a markdown outline (the mind map library's native input),
and persists the result keyed by ``source_id`` so a map is generated only once
per source.  It reuses the existing singletons (LLM fallback chain + FaissStore)
rather than building new infrastructure.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.mindmap.storage import MindMapStore
from core.generation.prompt_builder import PromptBuilder
from core.interfaces.llm import LLM
from core.storage.faiss_store import FaissStore
from observability.tracer import observe

__all__ = ["MindMapError", "MindMapService"]

logger = logging.getLogger(__name__)

# Context budget guards — a single source (e.g. a large GitHub repo) can store
# hundreds of chunks.  We sample a representative spread and cap the characters
# fed to the LLM so generation stays fast and never truncates mid-list.
#
# The budget is deliberately small: the primary provider (Groq's free tier) is
# capped at ~8000 tokens-per-minute, so each generation must fit comfortably
# inside that window.  A large prompt pushed a single request to roughly 4700
# tokens, which — under concurrent RAG activity — overran the limit and sent the
# request through the entire (currently rate-limited/end-of-life) fallback chain,
# making the button appear to hang.  Keeping the prompt small keeps every request
# well inside budget.
MAX_CHUNKS = 16
MAX_CHUNK_CHARS = 280
MAX_CONTEXT_CHARS = 6_000

# Hard cap on a single generation.  The provider chain can fall through several
# rate-limited/end-of-life endpoints, and each provider retries with exponential
# backoff — left unchecked that can hang the request for minutes, which the
# frontend reads as a stuck "Creating mind map…" button.  We bound the work so a
# request resolves (success or a clear error) instead of dragging on.
MAX_GENERATION_SECONDS = 45

_SYSTEM_PROMPT = (
    "You turn document content into an organised mind map. "
    "Produce ONLY a nested Markdown list that a minds-map renderer can parse "
    "directly — no prose, no code fences, no headings, no bullet glyphs other "
    "than '-'."
    "\n\n"
    "Rules:\n"
    "- Line 1 is the single root node: give it a short, concrete title for the "
    "source's overall subject.\n"
    "- Go no deeper than 3 levels (root → branch → leaf).\n"
    "- Capture the main topics, key points, and notable specifics (names, "
    "numbers, terminology) that are actually in the content. Do not invent "
    "facts.\n"
    "- Each branch should be a meaningful topic, each leaf a concrete detail. "
    "Keep every node to a short phrase.\n"
    "- Use a blank line between sibling root subtrees only if there is more than "
    "one truly distinct subject; otherwise keep a single root.\n"
    "- Respond in the same language as the source content."
)


class MindMapError(RuntimeError):
    """Raised when a mind map cannot be generated for a source."""


class MindMapService:
    """Builds and persists markdown mind maps from source chunks."""

    def __init__(
        self,
        store: MindMapStore,
        faiss: FaissStore,
        llm: LLM,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self._store = store
        self._faiss = faiss
        self._llm = llm
        self._prompt_builder = prompt_builder or PromptBuilder()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="mindmap_get")
    async def get(self, source_id: str) -> dict[str, Any] | None:
        return await self._store.get(source_id)

    @observe(name="mindmap_generate")
    async def generate(self, source_id: str) -> dict[str, Any]:
        """Return the persisted map for *source_id*, generating it if absent.

        Idempotent: if a map is already stored it is returned unchanged so the
        frontend never has to regenerate on a repeat visit.
        """
        existing = await self._store.get(source_id)
        if existing is not None:
            logger.info("mindmap: source_id=%s cached — returning stored map.", source_id)
            return existing

        chunks = await self._faiss.get_chunks_by_source_id(source_id)
        if not chunks:
            raise MindMapError(
                "No indexed content found for this source. Re-ingest it to "
                "generate a mind map."
            )

        title = self._resolve_title(source_id, chunks)
        sampled = _sample_chunks(chunks)
        user_prompt = self._build_prompt(source_id, title, sampled)

        start = time.perf_counter()
        try:
            markdown = await asyncio.wait_for(
                self._llm.generate(
                    user_prompt,
                    system_prompt=_SYSTEM_PROMPT,
                ),
                timeout=MAX_GENERATION_SECONDS,
            )
        except TimeoutError as exc:  # pragma: no cover - timing guard
            logger.exception(
                "mindmap: generation timed out after %.0fs for source_id=%s",
                MAX_GENERATION_SECONDS, source_id,
            )
            raise MindMapError(
                "Mind map generation timed out. The AI providers may be under "
                "rate limits — please try again in a little while."
            ) from exc
        except Exception as exc:  # pragma: no cover - provider failure surfaced to route
            logger.exception("mindmap: LLM generation failed for source_id=%s", source_id)
            raise MindMapError(
                "The AI provider could not generate a mind map. It may be at its "
                "rate limit or quota — please try again in a little while."
            ) from exc
        elapsed = (time.perf_counter() - start) * 1000

        markdown = _normalize_markdown(markdown)
        if not markdown:
            raise MindMapError("The AI provider returned no mind map to render.")

        saved = await self._store.upsert(
            source_id, title, markdown, len(sampled)
        )
        logger.info(
            "mindmap: generated for source_id=%s chunks=%d elapsed=%.1f ms",
            source_id, len(sampled), elapsed,
        )
        return saved

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _resolve_title(self, source_id: str, chunks) -> str:
        title = ""
        for chunk in chunks:
            meta = dict(chunk.metadata) if chunk.metadata else {}
            if meta.get("repo"):
                title = str(meta["repo"])
                break
            if meta.get("title"):
                title = str(meta["title"])
                break
            if meta.get("filename"):
                title = str(meta["filename"])
                break
        if not title:
            title = source_id.rsplit("/", 1)[-1]
        # A text loader may store the whole body as the title — keep the root
        # node short so the map stays scannable.
        title = title.strip()
        if len(title) > 64:
            title = title[:61].rstrip() + "..."
        return title or "Mind Map"

    def _build_prompt(self, source_id: str, title: str, chunks) -> str:
        lines: list[str] = []
        lines.append(f"Source: {title}  (id: {source_id})")
        lines.append(
            f"Build a mind map from its {len(chunks)} indexed chunk(s). "
            "Return only the Markdown list."
        )
        lines.append("---")
        for i, chunk in enumerate(chunks, start=1):
            text = (chunk.text or "").strip()[:MAX_CHUNK_CHARS]
            if not text:
                continue
            lines.append(f"[Chunk {i}]\n{text}")
            if sum(len(line) for line in lines) >= MAX_CONTEXT_CHARS:
                break
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _sample_chunks(chunks) -> list:
    """Return a representative spread of up to ``MAX_CHUNKS`` chunks.

    Uses stride sampling so a map built from a large source touches the whole
    document rather than only its first-page content.
    """
    n = len(chunks)
    if n <= MAX_CHUNKS:
        return list(chunks)
    step = n / MAX_CHUNKS
    picked = [chunks[int(i * step)] for i in range(MAX_CHUNKS)]
    logger.debug("mindmap: sampled %d of %d chunks (stride=%.2f).", len(picked), n, step)
    return picked


def _normalize_markdown(markdown: str) -> str:
    """Trim ML output to a clean, non-blank markdown list.

    Strips a leading code fence and root heading that some models add, leaving
    the nested '-'-prefixed list the mind map parser expects.
    """
    text = (markdown or "").strip()

    # Strip a single triple-backtick fenced block if the model wrapped the list.
    if text.startswith("```"):
        text = text.strip("`")
        # Drop a language tag on the opening line (e.g. ```markdown).
        text = text.split("\n", 1)[-1] if "\n" in text else text

    # Drop a trailing ### heading line if present after a leading heading.
    lines = text.splitlines()
    cleaned: list[str] = []
    started = False
    for line in lines:
        stripped = line.rstrip()
        if not stripped.strip():
            if started:
                cleaned.append(stripped)
            continue
        if stripped.lstrip().startswith("-#"):
            continue  # skip H1/H2/H3 heading lines
        started = True
        cleaned.append(stripped)
    return "\n".join(cleaned).strip()
