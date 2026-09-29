"""Parse and validate inline citation markers such as ``[1]`` or ``[1][3]``.

Why validation is not optional
------------------------------
Citation markers are produced by the model, and a model that is asked to cite
can cite a passage that was never supplied. Rendering ``[7]`` when five sources
exist produces a dead reference that looks authoritative, which is worse than
no citation at all: the reader's trust is the thing being spent.

So every marker is checked against the number of sources actually retrieved,
and an out-of-range marker is removed rather than shown. The alternative -
passing the model's numbering through untouched - would let a hallucinated
reference survive all the way to the screen.

Relationship to the grounding check
----------------------------------
:mod:`core.generation.grounding` asks whether the *answer* is supported by the
*context*. This module asks whether the *citations* point at passages that
exist. They are different failures and need different checks: an answer can be
perfectly faithful and still cite ``[9]`` of five sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A marker is a bracketed run of one or more digits: [1], [12], [1][3].
_MARKER = re.compile(r"\[(\d{1,2})\]")

# The model sometimes emits a grouped marker: [1, 3] or [1,3].
_GROUPED_MARKER = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")

# A citation stands on its own: it follows whitespace, a quote, or an opening
# bracket. When the digits directly follow an identifier character the bracket
# is a subscript, not a reference.
#
# This distinction is load-bearing for this product. Answers routinely contain
# code and array indexing - "model[0]", "df[1]", "rows[2]" - and treating
# those as citations silently deletes the subscript and corrupts the prose.
# In testing, "model[0]" became "model".
_SUBSCRIPT = re.compile(r"[\w.\]\)]")

# Markdown reference-style links look like [text][1] or [text]: but a bare
# numeric group is a citation, never a link definition, so the numeric-only
# pattern above cannot collide with one.
_TRAILING = re.compile(r"(?<=\d)\]_")


@dataclass(frozen=True)
class CitationSpan:
    """One validated citation.

    Attributes:
        marker: The normalised marker text as it should be displayed, e.g. "[1]".
        index:  Zero-based index into the sources list.
    """

    marker: str
    index: int


@dataclass(frozen=True)
class ParsedCitations:
    """Result of parsing an answer's citation markers.

    Attributes:
        text:        The answer with out-of-range markers removed, so the prose
                     is never left with a dangling "[9]".
        citations:   Every distinct validated citation, in order of appearance.
        discarded:   Marker strings that referred to no available source.
    """

    text: str
    citations: tuple[CitationSpan, ...]
    discarded: tuple[str, ...]


def _parse_one_bracket(inner: str) -> list[int]:
    """Turn the inside of a bracket group into zero-based source indices."""
    if re.fullmatch(r"\d{1,2}", inner.strip()):
        return [int(inner.strip()) - 1]
    indices: list[int] = []
    for part in inner.split(","):
        part = part.strip()
        if part.isdigit():
            indices.append(int(part) - 1)
    return indices


def parse_citations(answer: str, source_count: int) -> ParsedCitations:
    """Extract, validate and rewrite the citation markers in *answer*.

    Markers pointing outside the retrieved set are stripped from the text and
    reported in :attr:`ParsedCitations.discarded`, so a caller can log the
    model's miscounting rather than shipping a broken reference to the reader.

    Args:
        answer:       The generated answer, which may contain ``[n]`` markers.
        source_count: How many sources were actually retrieved. A marker is
                      kept only when its 1-based number is within this range.

    Returns:
        A :class:`ParsedCitations`. An answer with no markers yields the text
        unchanged, so this is safe to apply to every response.
    """
    if source_count <= 0 or "[" not in answer:
        return ParsedCitations(text=answer, citations=(), discarded=())

    kept: list[CitationSpan] = []
    seen: set[int] = set()
    discarded: list[str] = []
    out: list[str] = []
    cursor = 0

    # Grouped markers are matched first so "[1, 3]" is handled as a unit
    # rather than being left partially rewritten by the single-marker pattern.
    combined = re.compile(f"{_GROUPED_MARKER.pattern}|{_MARKER.pattern}")

    for match in combined.finditer(answer):
        raw = match.group(0)
        inner = raw[1:-1]
        # A bracket glued to an identifier is a subscript ("model[0]"), not a
        # citation. Leave it exactly as written.
        if match.start() > 0 and _SUBSCRIPT.search(answer[match.start() - 1]):
            continue
        indices = _parse_one_bracket(inner)
        if not indices:
            continue

        valid = [i for i in indices if 0 <= i < source_count]
        invalid = len(indices) - len(valid)
        if invalid:
            discarded.append(raw)

        if not valid:
            # Drop the marker entirely; keeping a dangling bracket would leave
            # visible debris in the prose. The preceding space goes with it so
            # the sentence does not end up as "in 2024 ." rather than "in 2024".
            start = match.start()
            while start > 0 and answer[start - 1] == " ":
                start -= 1
            out.append(answer[cursor:start])
            cursor = match.end()
            continue

        out.append(answer[cursor : match.start()])
        for i in valid:
            if i not in seen:
                seen.add(i)
                kept.append(CitationSpan(marker=f"[{i + 1}]", index=i))
        # Collapse a group into individual markers so each carries a single
        # index the UI can resolve.
        out.append("".join(f"[{i + 1}]" for i in valid))
        cursor = match.end()

    out.append(answer[cursor:])
    return ParsedCitations(
        text="".join(out),
        citations=tuple(kept),
        discarded=tuple(discarded),
    )
