"""Application service for Mind Map generation.

Layered:  route -> service -> (LLM + FaissStore) + MindMapStore.

The service gathers the selected sources' chunks from the vector store, asks
the LLM to condense them into a markdown outline (the mind map library's
native input), and persists the result keyed by the selection so a given set
is generated only once.  It reuses the existing singletons (LLM fallback chain
+ FaissStore) rather than building new infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.mindmap.schemas import composite_key
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

# Output budget.  The input is capped above, but the outline itself was not, so
# generation time scaled with however many branches the model felt like writing
# (a single source produced 65 lines and took ~77s on a free-tier provider).
# Latency here is output-bound, not input-bound, so bounding the outline is what
# actually shortens a request.  These are also what keeps the map scannable.
MAX_ROOT_BRANCHES = 8
MAX_OUTLINE_LINES = 40

# Hard cap on a single generation.  The provider chain can fall through several
# rate-limited/end-of-life endpoints, and each provider retries with exponential
# backoff — left unchecked that can hang the request for minutes, which the
# frontend reads as a stuck "Creating mind map…" button.  We bound the work so a
# request resolves (success or a clear error) instead of dragging on.
#
# Raised from 45s to 135s: a multi-source selection aggregates chunks from every
# chosen source into one prompt, so the same budget that suited a single source
# left too little room for a combined map.  The client timeout is set above this
# value (see MIND_MAP_TIMEOUT_MS in frontend/src/services/api.js) so the server
# always gets to return its explicit timeout error rather than the browser
# aborting the request with an opaque network failure.
MAX_GENERATION_SECONDS = 135

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
    f"- Keep it tight: at most {MAX_ROOT_BRANCHES} top-level branches and about "
    f"{MAX_OUTLINE_LINES} lines in total. Prefer fewer, broader branches over "
    "many narrow ones — do not pad the outline to fill space.\n"
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

    def swap_llm(self, llm: LLM) -> None:
        """Point Mind Map generation at the currently served LLM."""
        self._llm = llm

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="mindmap_get")
    async def get(self, key: str) -> dict[str, Any] | None:
        """Return a stored map by key, or ``None`` when nothing is cached.

        ``key`` is a raw source id for a single source, or a composite key from
        :func:`~app.mindmap.schemas.composite_key` for a multi-source selection.
        """
        return await self._store.get(key)

    @observe(name="mindmap_generate")
    async def generate(
        self,
        source_ids: list[str] | str,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Return the persisted map for the selection, generating it if absent.

        Idempotent: if a map is already stored for the same selection it is
        returned unchanged, so the frontend never regenerates on a repeat visit.
        ``source_ids`` accepts a list (the workspace can select several sources
        at once) or a bare string for the single-source case.
        """
        if isinstance(source_ids, str):
            source_ids = [source_ids]
        ids = [s.strip() for s in source_ids if s and s.strip()]
        # De-duplicate while keeping the caller's order for title resolution.
        seen: set[str] = set()
        selected: list[str] = []
        for s in ids:
            if s not in seen:
                seen.add(s)
                selected.append(s)
        if not selected:
            raise MindMapError("Select at least one source to build a mind map.")

        key = composite_key(selected)

        if not refresh:
            existing = await self._store.get(key)
            if existing is not None:
                logger.info("mindmap: key=%s cached — returning stored map.", key)
                return existing

        chunks = await self._collect_chunks(selected)
        if not chunks:
            raise MindMapError(
                "No indexed content found for the selected source(s). Re-ingest them to generate a mind map."
            )

        title = self._resolve_title(selected, chunks)
        sampled = _sample_chunks(chunks)
        user_prompt = self._build_prompt(selected, title, sampled)

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
                "mindmap: generation timed out after %.0fs for key=%s",
                MAX_GENERATION_SECONDS,
                key,
            )
            raise MindMapError(
                "Mind map generation timed out. The AI providers may be under "
                "rate limits — please try again in a little while."
            ) from exc
        except Exception as exc:  # pragma: no cover - provider failure surfaced to route
            logger.exception("mindmap: LLM generation failed for key=%s", key)
            raise MindMapError(
                "The AI provider could not generate a mind map. It may be at its "
                "rate limit or quota — please try again in a little while."
            ) from exc
        elapsed = (time.perf_counter() - start) * 1000

        markdown = _normalize_markdown(markdown)
        if not markdown:
            raise MindMapError("The AI provider returned no mind map to render.")

        saved = await self._store.upsert(key, title, markdown, len(sampled))
        logger.info(
            "mindmap: generated for key=%s sources=%d chunks=%d elapsed=%.1f ms",
            key,
            len(selected),
            len(sampled),
            elapsed,
        )
        return saved

    async def _collect_chunks(self, source_ids: list[str]) -> list:
        """Gather chunks for every selected source, skipping unknown ones.

        A selection can name a source that has since been deleted, so a missing
        one must not sink the whole map — it is skipped and the rest still build.
        """
        gathered: list = []
        for sid in source_ids:
            try:
                found = await self._faiss.get_chunks_by_source_id(sid)
            except Exception:
                logger.exception("mindmap: chunk lookup failed for source_id=%s", sid)
                continue
            if found:
                gathered.extend(found)
            else:
                logger.warning("mindmap: no indexed chunks for source_id=%s — skipping.", sid)
        return gathered

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _resolve_title(self, source_ids: list[str], chunks) -> str:
        """Derive the root-node title from the selected sources' metadata."""
        titles: list[str] = []
        for chunk in chunks:
            meta = dict(chunk.metadata) if chunk.metadata else {}
            label = ""
            for field in ("repo", "title", "filename"):
                if meta.get(field):
                    label = str(meta[field]).strip()
                    break
            if label and label not in titles:
                titles.append(label)

        if not titles:
            titles = [s.rsplit("/", 1)[-1] for s in source_ids]

        # A text loader may store the whole body as the title — keep the root
        # node short so the map stays scannable.
        title = titles[0] if len(titles) == 1 else f"{len(titles)} sources"
        title = title.strip()
        if len(title) > 64:
            title = title[:61].rstrip() + "..."
        return title or "Mind Map"

    def _build_prompt(self, source_ids: list[str], title: str, chunks) -> str:
        lines: list[str] = []
        if len(source_ids) == 1:
            lines.append(f"Source: {title}  (id: {source_ids[0]})")
        else:
            joined = ", ".join(source_ids)
            lines.append(f"Sources ({len(source_ids)}): {joined}")
            lines.append(f"Overall topic: {title}")
            lines.append(
                "Build one mind map covering the shared themes across every source. "
                "Group branches by theme rather than by source, and only add a "
                "source-specific branch where a source has content no other source "
                "covers."
            )
        lines.append(f"Build a mind map from its {len(chunks)} indexed chunk(s). Return only the Markdown list.")
        lines.append("---")
        for i, chunk in enumerate(chunks, start=1):
            text = (chunk.text or "").strip()[:MAX_CHUNK_CHARS]
            if not text:
                continue
            label = getattr(chunk, "source_id", None) or source_ids[0]
            lines.append(f"[Chunk {i} — {label}]\n{text}")
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
        text_only = stripped.lstrip()
        # Skip heading lines in either form a model emits them: a real markdown
        # heading ("### Topic") or a list item that is really a heading
        # ("- # Topic").  The renderer expects a plain nested list.
        if text_only.startswith("#") or text_only.startswith("-#"):
            continue
        started = True
        cleaned.append(stripped)
    return _cap_outline("\n".join(cleaned).strip())


def _cap_outline(markdown: str) -> str:
    """Enforce the outline budget the prompt asked for.

    A backstop only: the prompt already caps branches and depth, but a model
    that ignores it would still make us pay for every extra token.  Trimming
    after the fact bounds the stored map and keeps the render fast.

    Depth is capped at three levels, and the total line count at
    ``MAX_OUTLINE_LINES``.  A truncation is only accepted if the cut still
    yields a well-formed outline (a root plus at least one child), otherwise the
    original is kept rather than storing a stub.
    """
    if not markdown:
        return markdown

    lines = markdown.splitlines()
    kept: list[str] = []
    for line in lines:
        if not line.strip():
            if kept:
                kept.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        # Two spaces per level, so >= 6 spaces of indent is the fourth level.
        if indent >= 6:
            continue
        kept.append(line)
        if len([ln for ln in kept if ln.strip()]) >= MAX_OUTLINE_LINES:
            break

    trimmed = "\n".join(kept).strip()
    non_blank = [ln for ln in trimmed.splitlines() if ln.strip()]
    if len(non_blank) < 2:
        # Truncation left nothing useful — prefer the model's full answer.
        return markdown
    return trimmed
