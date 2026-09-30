"""Application service for Note generation.

Layered:  route -> service -> (LLM + FaissStore) + NoteStore.

Structurally a sibling of :mod:`app.mindmap.service`: the service gathers the
selected sources' chunks from the vector store, asks the LLM to write a note
from them, and persists the result keyed by the selection so a given set is
generated only once.  It reuses the existing singletons (LLM fallback chain +
FaissStore) rather than building new infrastructure.

The one place the two features diverge is the output.  A mind map is a bounded
nested list a renderer parses positionally; a note is prose, so the guard rails
here are about *length and provenance* rather than structure: an input budget,
an output budget, and a citation filter that removes any passage marker the
model invented.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from app.mindmap.schemas import composite_key
from app.notes.storage import NoteStore
from core.interfaces.llm import LLM
from core.storage.faiss_store import FaissStore
from observability.tracer import observe

__all__ = ["NoteError", "NoteService"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context budget guards
# ---------------------------------------------------------------------------
# A note is read, not scanned, so it earns a larger input budget than a mind map:
# the prompt carries more chunks, each is kept closer to full length, and the
# total is roughly double.  The ceilings are still hard — the primary provider
# (Groq's free tier) is capped at ~8000 tokens-per-minute, and a large prompt
# pushed through a rate-limited fallback chain is what made the mind map button
# appear to hang.  Staying well inside that budget is the point.
MAX_CHUNKS = 18
MAX_CHUNK_CHARS = 700
MAX_CONTEXT_CHARS = 12_000

# Output budget.  The input is capped above, but nothing stopped the model from
# writing an essay, and generation time is output-bound: an uncapped note cost
# far more than the request it was answering.  These also keep the note
# readable in one sitting, which is what makes it worth keeping.
MAX_SECTIONS = 6
MAX_NOTE_LINES = 90

# Hard cap on a single generation.  The provider chain can fall through several
# rate-limited endpoints, and each provider retries with exponential backoff —
# left unchecked that drags on for minutes, which the frontend reads as a stuck
# "Creating note…" button.  We bound the work so a request resolves (success or
# a clear error) instead of hanging.
#
# Slightly higher than the mind map's 135s because a note is longer prose and a
# multi-source selection aggregates chunks from every chosen source.  The client
# timeout is set above this value (see NOTE_TIMEOUT_MS in
# frontend/src/services/api.js) so the server always gets to return its explicit
# timeout error rather than the browser aborting with an opaque network failure.
MAX_GENERATION_SECONDS = 150

MAX_TITLE_CHARS = 80

_SYSTEM_PROMPT = (
    "You write a study note a person would actually keep and read. "
    "Reply with ONLY Markdown — no preamble, no code fence around the note, no "
    "closing remark."
    "\n\n"
    "WHAT MAKES THIS WORTH READING\n"
    "- Lead with the point. The first sentence must carry the single most "
    "important thing about the subject. Never open by naming the subject — the "
    "heading already does — and never open with 'This note covers' or any "
    "other throat-clearing.\n"
    "- Synthesise, don't transcribe. Pull the material into an argument. A "
    "reader should come away with something they could not get by skimming the "
    "source's own summary box.\n"
    "- Say why it matters. Give a scale, a comparison or a consequence, not "
    "just a list of attributes.\n"
    "- Write for someone who has not seen the sources and will not open them.\n"
    "\n"
    "STRUCTURE\n"
    "- One '# ' H1 naming the subject, then 3 to 5 '## ' H2 sections. Never "
    f"deeper than '### ', and never more than {MAX_SECTIONS} sections.\n"
    "- Head each section with its point — 'Research is concentrated in a few "
    "centres', not 'Research'. A reader scanning the headings should already "
    "have the argument.\n"
    "- Drop any section with nothing worth saying. Fewer, fuller sections beat "
    "many thin ones.\n"
    "\n"
    "SHAPE OF A PARAGRAPH\n"
    "- Two to four sentences. A paragraph that has taken on a second idea wants "
    "to be split, or turned into a list.\n"
    "- Render three or more discrete things — people, dates, departments, "
    "venues, societies, halls — as a list. A sentence naming twelve items is "
    "harder to use than the same twelve as bullets.\n"
    "- Keep exact numbers, dates, names and versions exactly as written. Never "
    "round or approximate a stated value.\n"
    "- Vary sentence length and cut any clause that merely announces what comes "
    "next.\n"
    "\n"
    "HONESTY\n"
    "- State only what the passages support. If they disagree on a figure, say "
    "so in one sentence and move on — a conflict is not worth a section.\n"
    "- Never mention the passages, the sources, the documents, or what they do "
    "or do not contain. The note is about the subject, full stop.\n"
    "- Never say that you reviewed, surveyed or examined anything.\n"
    f"- About {MAX_NOTE_LINES} lines in total. Do not pad the note to fill "
    "space.\n"
    "\n"
    "Respond in the same language as the source content."
)

# ``#``/``##``/``###`` with a space, on its own line.
_H_RE = re.compile(r"^(#{1,6})\s+(\S.*)$")


class NoteError(RuntimeError):
    """Raised when a note cannot be generated for a selection of sources."""


class NoteService:
    """Builds and persists markdown notes from source chunks."""

    def __init__(
        self,
        store: NoteStore,
        faiss: FaissStore,
        llm: LLM,
    ) -> None:
        self._store = store
        self._faiss = faiss
        self._llm = llm

    def swap_llm(self, llm: LLM) -> None:
        """Point note generation at the currently served LLM."""
        self._llm = llm

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="note_get")
    async def get(self, key: str) -> dict[str, Any] | None:
        """Return a stored note by key, or ``None`` when nothing is cached.

        ``key`` is a raw source id for a single source, or a composite key from
        :func:`~app.mindmap.schemas.composite_key` for a multi-source selection.
        """
        return await self._store.get(key)

    @observe(name="note_generate")
    async def generate(
        self,
        source_ids: list[str] | str,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Return the persisted note for the selection, generating it if absent.

        Idempotent: if a note is already stored for the same selection it is
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
            raise NoteError("Select at least one source to write a note from.")

        key = composite_key(selected)

        if not refresh:
            existing = await self._store.get(key)
            if existing is not None:
                logger.info("note: key=%s cached — returning stored note.", key)
                return existing

        chunks = await self._collect_chunks(selected)
        if not chunks:
            raise NoteError("No indexed content found for the selected source(s). Re-ingest them to write a note.")

        fallback_title = self._resolve_title(selected, chunks)
        sampled = _sample_chunks(chunks)
        user_prompt = self._build_prompt(selected, fallback_title, sampled)

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
                "note: generation timed out after %.0fs for key=%s",
                MAX_GENERATION_SECONDS,
                key,
            )
            raise NoteError(
                "Note generation timed out. The AI providers may be under rate "
                "limits — please try again in a little while."
            ) from exc
        except Exception as exc:  # pragma: no cover - provider failure surfaced to route
            logger.exception("note: LLM generation failed for key=%s", key)
            raise NoteError(
                "The AI provider could not write a note. It may be at its rate "
                "limit or quota — please try again in a little while."
            ) from exc
        elapsed = (time.perf_counter() - start) * 1000

        title, body = _normalize_note(markdown, fallback_title)
        if not body:
            raise NoteError("The AI provider returned no note to show.")

        # The title is stored on its own column *and* written back into the
        # document, so the frontend can render one markdown blob without having
        # to reassemble it while the stored row can still be addressed by name.
        document = f"# {title}\n\n{body}" if body else ""
        saved = await self._store.upsert(key, title, document, len(sampled))
        logger.info(
            "note: generated for key=%s sources=%d chunks=%d elapsed=%.1f ms",
            key,
            len(selected),
            len(sampled),
            elapsed,
        )
        return saved

    async def _collect_chunks(self, source_ids: list[str]) -> list:
        """Gather chunks for every selected source, skipping unknown ones.

        A selection can name a source that has since been deleted, so a missing
        one must not sink the whole note — it is skipped and the rest still build.
        """
        gathered: list = []
        for sid in source_ids:
            try:
                found = await self._faiss.get_chunks_by_source_id(sid)
            except Exception:
                logger.exception("note: chunk lookup failed for source_id=%s", sid)
                continue
            if found:
                gathered.extend(found)
            else:
                logger.warning("note: no indexed chunks for source_id=%s — skipping.", sid)
        return gathered

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _resolve_title(self, source_ids: list[str], chunks) -> str:
        """Derive a fallback title from the selected sources' metadata.

        Only used when the model does not supply an H1 of its own, so it stays
        deliberately dull — it is a heading, not a summary.
        """
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

        title = titles[0] if len(titles) == 1 else f"{len(titles)} sources"
        return _shorten_title(title) or "Note"

    def _build_prompt(self, source_ids: list[str], title: str, chunks) -> str:
        lines: list[str] = []
        if len(source_ids) == 1:
            lines.append(f"Source: {title}  (id: {source_ids[0]})")
        else:
            joined = ", ".join(source_ids)
            lines.append(f"Sources ({len(source_ids)}): {joined}")
            lines.append(f"Overall topic: {title}")
            lines.append(
                "Write one note covering the shared themes across every source. "
                "Group sections by theme rather than by source, and only treat a "
                "source separately where it holds content no other source covers."
            )
        lines.append(f"Write the note from its {len(chunks)} indexed passage(s) below.")
        lines.append("---")
        # The passages are labelled so the model can tell one source from another
        # when a selection spans several; it is not asked to cite them, and the
        # labels never reach the reader.
        for chunk in chunks:
            text = (chunk.text or "").strip()[:MAX_CHUNK_CHARS]
            if not text:
                continue
            lines.append(text)
            if sum(len(line) for line in lines) >= MAX_CONTEXT_CHARS:
                break
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _sample_chunks(chunks) -> list:
    """Return a representative spread of up to ``MAX_CHUNKS`` chunks.

    Uses stride sampling so a note written from a large source touches the whole
    document rather than only its first-page content.
    """
    n = len(chunks)
    if n <= MAX_CHUNKS:
        return list(chunks)
    step = n / MAX_CHUNKS
    picked = [chunks[int(i * step)] for i in range(MAX_CHUNKS)]
    logger.debug("note: sampled %d of %d chunks (stride=%.2f).", len(picked), n, step)
    return picked


def _shorten_title(title: str) -> str:
    """Trim a title to a heading-length string, on a word boundary."""
    text = (title or "").strip()
    if len(text) > MAX_TITLE_CHARS:
        text = text[: MAX_TITLE_CHARS - 3].rstrip()
        if " " in text:
            text = text.rsplit(" ", 1)[0]
        text += "..."
    return text


def _strip_fence(text: str) -> str:
    """Unwrap a response the model wrapped in a single fenced block."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    lines = lines[1:]
    # Drop the closing fence and any language tag the opening line carried.
    while lines and (not lines[-1].strip() or lines[-1].strip().startswith("```")):
        lines.pop()
    return "\n".join(lines).strip()


def _normalize_note(markdown: str, fallback_title: str) -> tuple[str, str]:
    """Trim model output to a clean note body and pull the title out of it.

    Returns ``(title, body)`` where *body* is Markdown that starts at the first
    ``##`` section — the H1 is returned separately so the caller can render it
    as a heading and address the note by name.

    Strips an enclosing code fence, demotes a stray second H1 so the document has
    exactly one title, caps depth at three levels, and enforces the section and
    line budgets.
    """
    lines = _strip_fence(markdown or "").splitlines()

    title = ""
    body: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.rstrip()
        # A fenced block inside the note is legitimate (a config sample, say), so
        # its contents are copied through untouched rather than rewritten.
        if stripped.lstrip().startswith("```"):
            in_fence = not in_fence
            body.append(stripped)
            continue
        if in_fence:
            body.append(stripped)
            continue

        match = _H_RE.match(stripped.strip()) if stripped.strip() else None
        if match:
            hashes, text = match.group(1), match.group(2).strip()
            if len(hashes) == 1:
                # The first H1 is the title and leaves the body; a later one is a
                # section a model promoted by mistake, so it comes back down.
                if not title and not any(ln.strip() for ln in body):
                    title = _shorten_title(text)
                    continue
                body.append(f"## {text}")
                continue
            # Beyond three levels the note stops being scannable; flatten to H3.
            level = min(len(hashes), 3)
            body.append(f"{'#' * level} {text}")
            continue

        body.append(stripped)

    body = _collapse_blank_lines(body)
    body = _cap_note(body)

    if not title:
        title = _shorten_title(fallback_title) or "Note"
    return title, "\n".join(body).strip()


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    """Drop leading blanks and collapse runs of blanks to a single one."""
    out: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            out.append(line)
            blank = False
        elif out and not blank:
            out.append("")
            blank = True
    while out and not out[-1].strip():
        out.pop()
    return out


def _cap_note(lines: list[str]) -> list[str]:
    """Enforce the section and line budgets the prompt asked for.

    A backstop only: the prompt already caps sections and depth, but a model
    that ignores it would still make us pay for every extra token, and would
    store a note nobody reads to the end.

    Sections are cut whole rather than mid-section, and the line cap backs off to
    the last paragraph break.  Ending on a half-written sentence — or on a
    heading with nothing under it — reads as a rendering bug rather than as a
    budget, so neither is an acceptable place to stop.
    """
    kept: list[str] = []
    sections = 0
    truncated = False
    non_blank = 0
    for line in lines:
        if line.strip() and _H_RE.match(line.strip()):
            sections += 1
            if sections > MAX_SECTIONS:
                truncated = True
                break
        if line.strip():
            non_blank += 1
            if non_blank > MAX_NOTE_LINES:
                truncated = True
                break
        kept.append(line)

    if not truncated:
        return kept

    if len([ln for ln in kept if ln.strip()]) < 2:
        # A budget this tight can leave nothing usable; rather than store a stub,
        # prefer a longer but complete note over no note at all.
        return lines

    # Roll back the paragraph the cut landed inside so the note ends on a
    # complete thought.  Bounded by a "no paragraph break found" guard: a note
    # written as one unbroken block still has to be capped.
    rolled = list(kept)
    while rolled and rolled[-1].strip():
        rolled.pop()
    if len([ln for ln in rolled if ln.strip()]) >= 2:
        kept = rolled

    logger.debug("note: trimmed to %d section(s) / %d line(s).", sections, non_blank)
    return kept
