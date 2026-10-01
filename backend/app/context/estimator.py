"""Estimating what a source selection will cost, and how much of it is usable.

Selecting sources is the workspace's primary control, but it has always been
close to cosmetic: retrieval pulls a fixed 20 candidates and reranking keeps the
best 5, so adding a second, third or tenth source barely changes what reaches
the model.  Measured on a real corpus, the whole knowledge base is ~71k tokens
while a single answer is built from 5 chunks — well under 3k.  A user who
selected four documents to reason across them was mostly selecting *exclusions*.

This module makes that visible, and gives the number something to act on:

* :func:`estimate_context` prices a selection without running retrieval — no
  embedding call, no LLM call, no reranker.  It reads the chunk store directly,
  so it is cheap enough to call on every selection change.
* :func:`resolve_context_depth` turns a coarse user-facing depth into the
  concrete retrieval/rerank limits, so "more context" actually means more
  context rather than a label that changes nothing.

Both are deliberately conservative about what they claim.  The estimator reports
the size of the *material available*, not the size of the prompt that will be
built, and says which of the two it is reporting — conflating them would be the
same kind of dishonesty this feature exists to remove.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from core.chunking.text_chunker import get_token_len

__all__ = [
    "CONTEXT_DEPTHS",
    "ContextDepth",
    "SelectionEstimate",
    "SourceCost",
    "estimate_context",
    "resolve_context_depth",
]

logger = logging.getLogger(__name__)

ContextDepth = Literal["focused", "balanced", "broad"]

# Coarse depths, each a real change to the retrieval limits.  These are the
# values the UI cycles through; the numbers behind them are the pipeline's, not
# arbitrary UI constants.
#
#   focused  — default. Few sources, few chunks. Fastest, and right when one
#              document holds the answer.
#   balanced — more sources and more chunks each, so several documents can be
#              reasoned across. This is what "select several sources" should do.
#   broad    — as much of the selection as the prompt will hold. Slowest, and
#              the setting to reach for when the answer needs the whole corpus.
#
# ``per_source_cap`` is now a real pipeline limit, passed through to the
# reranker's per-source ceiling, so widening the depth reads more of the
# material that is selected.  It is what makes the depth control work for a
# single selected document: with one source there is no crowding to prevent, and
# top_k_rerank alone is not enough, because the reranker will not draw more than
# the cap from one document.
#
# A repository is not limited the same way — its coverage groups are file paths,
# ``focused`` is 5 rather than 4 because that is what a single-source selection
# already received before the cap was plumbed through.  Lowering it would have
# quietly made the default answer from *less* than it does now, which is the
# opposite of what a user who widens the depth is asking for.
CONTEXT_DEPTHS: dict[str, dict[str, int]] = {
    "focused": {"max_sources": 2, "top_k_retrieval": 20, "top_k_rerank": 5, "per_source_cap": 5},
    "balanced": {"max_sources": 6, "top_k_retrieval": 40, "top_k_rerank": 12, "per_source_cap": 8},
    "broad": {"max_sources": 25, "top_k_retrieval": 80, "top_k_rerank": 25, "per_source_cap": 12},
}

# Above this, a depth change is more likely to be refused or truncated by the
# provider than to change the answer, so the UI is told so rather than letting
# the user raise the depth and see nothing change.
DIMINISHING_RETURNS_TOKENS = 60_000


@dataclass(frozen=True)
class SourceCost:
    """What one selected source contributes to the available material."""

    source_id: str
    title: str
    chunk_count: int
    char_count: int
    token_count: int


@dataclass
class SelectionEstimate:
    """The cost of a selection, plus how much of it will actually be used."""

    source_count: int
    sources: list[SourceCost] = field(default_factory=list)
    total_char_count: int = 0
    total_token_count: int = 0
    # What the current depth would actually put in the prompt.  Deliberately
    # reported next to the totals above rather than instead of them: the gap
    # between the two is the whole point.
    prompt_token_estimate: int = 0
    prompt_chunk_limit: int = 0
    effective_depth: str = "focused"
    per_source_cap: int = 4
    beyond_diminishing_returns: bool = False
    dropped_source_ids: list[str] = field(default_factory=list)
    missing_source_ids: list[str] = field(default_factory=list)

    @property
    def usable_fraction(self) -> float:
        """Share of the selected material that reaches the model.

        1.0 when everything fits, falling towards 0 as the selection outgrows
        the chunk cap.  A value of 0.02 means selecting a document changed the
        answer almost not at all, which is worth saying out loud.
        """
        if self.total_token_count <= 0:
            return 0.0
        return min(1.0, self.prompt_token_estimate / self.total_token_count)


def _title_for(chunks: list) -> str:
    """A display title for a source, matching how the source list resolves it."""
    if not chunks:
        return "Untitled source"
    meta = getattr(chunks[0], "metadata", None) or {}
    if str(meta.get("source_type") or meta.get("source") or "") == "github" and meta.get("repo"):
        return str(meta["repo"])
    return str(meta.get("title") or "Untitled source")


async def estimate_context(
    *,
    source_ids: Iterable[str] | None,
    chunk_index,
    depth: str = "focused",
) -> SelectionEstimate:
    """Price a source selection without retrieving anything.

    Args:
        source_ids: The user's selection.  ``None`` or empty means the whole
            knowledge base, matching how a query with no scope is interpreted.
        chunk_index: Anything exposing ``get_chunks_by_source_id``; in practice
            the FAISS store.
        depth:      A key of :data:`CONTEXT_DEPTHS`.

    Returns:
        A populated :class:`SelectionEstimate`.  Sources present in the request
        but absent from the index are listed in ``missing_source_ids`` rather
        than being silently dropped, because "I selected it" and "it is
        contributing" are different facts.
    """
    wanted = [s for s in (source_ids or []) if s and s.strip()]
    limits = CONTEXT_DEPTHS.get(depth, CONTEXT_DEPTHS["focused"])

    all_chunks = await chunk_index.get_chunks_by_source_id(None)
    grouped: dict[str, list] = {}
    for chunk in all_chunks:
        grouped.setdefault(chunk.source_id, []).append(chunk)

    if wanted:
        missing = [sid for sid in wanted if sid not in grouped]
        groups = [(sid, grouped[sid]) for sid in wanted if sid in grouped]
    else:
        missing = []
        groups = sorted(grouped.items())

    costs: list[SourceCost] = []
    total_chars = 0
    total_tokens = 0
    for source_id, chunks in groups:
        text = "\n\n".join(c.text for c in chunks)
        tokens = get_token_len(text)
        costs.append(
            SourceCost(
                source_id=source_id,
                title=_title_for(chunks),
                chunk_count=len(chunks),
                char_count=len(text),
                token_count=tokens,
            )
        )
        total_chars += len(text)
        total_tokens += tokens

    # A depth caps how many sources participate, so the prompt estimate is over
    # the sources it would keep, not over everything the user selected.  Sources
    # beyond the cap still count in the totals: they are in the selection, and
    # the user should see that they were dropped.
    kept = costs[: limits["max_sources"]]
    prompt_tokens = sum(c.token_count for c in kept) if costs else 0

    # The ceiling on prompt material is set by chunks, not by the selection: the
    # reranker keeps at most `top_k_rerank` chunks overall, and no more than
    # `per_source_cap` from any one document.  Reporting the min of the two is
    # what makes "you selected 40k tokens, 3k will be used" legible.
    chunk_ceiling = limits["top_k_rerank"] * 512
    per_source_ceiling = sum(min(c.token_count, limits["per_source_cap"] * 512) for c in kept)
    capped = min(prompt_tokens, chunk_ceiling, per_source_ceiling)

    return SelectionEstimate(
        source_count=len(costs),
        sources=costs,
        total_char_count=total_chars,
        total_token_count=total_tokens,
        prompt_token_estimate=capped,
        prompt_chunk_limit=limits["top_k_rerank"],
        # The requested depth is the depth that runs.  It used to be clamped
        # down when the selection was small, on the theory that a wider setting
        # over two sources "would behave like a narrower one".  That was false:
        # every depth differs in top_k_rerank and per_source_cap as well as
        # max_sources, so a wider depth reads strictly more of the material
        # that is there.  With one source selected the old clamp discarded the
        # user's only lever, because per-source crowding — the thing the caps
        # exist to prevent — cannot happen with a single source.  The caps are
        # already hard limits that cannot overflow the prompt, so honouring the
        # request is safe and the estimate simply reports what will run.
        effective_depth=depth if depth in CONTEXT_DEPTHS else "focused",
        per_source_cap=limits["per_source_cap"],
        beyond_diminishing_returns=total_tokens > DIMINISHING_RETURNS_TOKENS,
        # Sources the depth would not use, so the UI can name them rather than
        # showing a selection count that does not match what is sent.
        dropped_source_ids=[c.source_id for c in costs[limits["max_sources"] :]],
        missing_source_ids=missing,
    )


def resolve_context_depth(depth: str | None) -> dict[str, int]:
    """Resolve a user-facing depth to concrete pipeline limits.

    An unknown or absent value falls back to ``focused``, the pipeline default,
    so a bad client cannot widen the context window by accident.
    """
    return dict(CONTEXT_DEPTHS.get(depth or "focused", CONTEXT_DEPTHS["focused"]))
