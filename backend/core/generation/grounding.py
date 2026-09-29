"""Check that specific factual claims in an answer appear in the retrieved context.

Why this exists
---------------
Confidence is currently derived from retrieval scores alone. That measures how
well the retrieved chunks matched the *question*, not whether the *answer* is
supported by them. An answer can therefore be reported as high-confidence while
asserting something the corpus never said.

The system prompt explicitly asks the model to synthesise, to add the "so what",
and to draw comparisons, so the answer is *expected* to contain wording absent
from the source. A whole-answer overlap score would flag correct synthesis as
hallucination. So this deliberately does not score vocabulary similarity.

What it checks instead is the narrow class of tokens that are verifiable
verbatim and wrong to invent: figures, percentages, versions, identifiers and
dates. "The Random Forest reports 97.06% accuracy" either contains a supported
figure or it does not, and no amount of good prose can rescue an invented one.

This runs as pure string work with no model call. That is a deliberate
constraint: a verifier that needs an LLM would add seconds to every request,
which is the cost this pipeline has just spent real work removing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Claim patterns, ordered by how confidently they must be verbatim in context.
#
# Deliberately excluded:
#   * bare small integers ("three", "2") - ordinals, list positions and counts
#     are phrased too freely to check without false positives
#   * sentences and general vocabulary - the prompt requires synthesis
#   * proper nouns - often legitimately rendered differently from the source
_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Percentages, with or without a sign: 97.06%, 12 %
    re.compile(r"\d+(?:\.\d+)?\s?%"),
    # Version strings: v1.2.3, 0.121.0, 20b. Requires a digit after a dot so a
    # sentence-ending period ("released in 2024.") is not read as a version.
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)+\b", re.IGNORECASE),
    # Currency amounts: $1,200.00, USD 45
    re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*\s?(?:USD|EUR|GBP|dollars?)\b", re.IGNORECASE),
    # ISO-ish dates: 2024-01-31
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # Multi-decimal measurements: 0.9453, 97.06. At least one decimal point
    # keeps this away from integers and years.
    re.compile(r"\b\d+\.\d{2,}\b"),
)

# Trailing punctuation and markdown decoration that must not defeat a match.
_TRIM = " \t\n.,;:!?*_`\"'()[]{}"

# Answers below this length carry no checkable claims, and a short answer is
# not a reason to penalise: "No information is available" is a refusal, and
# refusing correctly must never lower confidence.
_MIN_ANSWER_CHARS = 24


@dataclass(frozen=True)
class GroundingReport:
    """Outcome of a grounding check.

    Attributes:
        checked:       Number of distinct claims found in the answer.
        supported:     Claims found verbatim in the retrieved context.
        unsupported:   The claim strings with no match in context, in order.
        is_grounded:   True when nothing checkable went unsupported.
    """

    checked: int
    supported: int
    unsupported: tuple[str, ...]

    @property
    def is_grounded(self) -> bool:
        return not self.unsupported

    @property
    def support_ratio(self) -> float:
        """Share of checkable claims that are supported, 1.0 when none exist."""
        if self.checked == 0:
            return 1.0
        return self.supported / self.checked


def _normalise(text: str) -> str:
    """Lowercase and collapse whitespace so line breaks cannot hide a match."""
    return re.sub(r"\s+", " ", text.lower())


def _is_inside(span: tuple[int, int], others: list[tuple[int, int]]) -> bool:
    """True when *span* falls within one of *others* (already-matched claims)."""
    start, end = span
    return any(o_start <= start and end <= o_end for o_start, o_end in others)


def extract_claims(answer: str) -> list[str]:
    """Return the distinct checkable claims present in *answer*.

    Claims are normalised (trimmed of decoration) and deduplicated while
    preserving order, so a figure repeated in the answer is checked once.
    Overlapping matches are also collapsed: in "$1,200.00" the currency pattern
    claims the whole amount and the multi-decimal pattern would otherwise claim
    "200.00" from inside it, double-counting one invented figure as two.
    """
    seen: set[str] = set()
    spans: list[tuple[int, int]] = []
    claims: list[str] = []
    for pattern in _CLAIM_PATTERNS:
        for match in pattern.finditer(answer):
            if _is_inside(match.span(), spans):
                continue
            spans.append(match.span())
            claim = match.group(0).strip(_TRIM)
            key = _normalise(claim)
            # Ignore a trivially short token; it adds no evidence and would
            # only dilute the ratio.
            if not key or len(key) < 2:
                continue
            if key in seen:
                continue
            seen.add(key)
            claims.append(claim)
    return claims


def check_grounding(answer: str, chunks: list[str]) -> GroundingReport:
    """Verify that *answer*'s checkable claims appear in *chunks*.

    Args:
        answer:  The generated answer text.
        chunks:  Full text of the retrieved chunks the answer was built from.
                 Must be the complete chunk text, not a truncated preview: a
                 figure commonly sits past the first 200 characters.

    Returns:
        A :class:`GroundingReport`. An answer with no checkable claims is
        reported as grounded, since there is nothing that could be unsupported.
    """
    claims = extract_claims(answer)
    if not claims or len(answer.strip()) < _MIN_ANSWER_CHARS:
        return GroundingReport(checked=0, supported=0, unsupported=())

    haystack = _normalise(" \n ".join(chunks))
    # Match on whitespace-collapsed context so a figure split across a line
    # break in the source still counts as present.
    unsupported = tuple(claim for claim in claims if _normalise(claim) not in haystack)
    checked = len(claims)
    return GroundingReport(
        checked=checked,
        supported=checked - len(unsupported),
        unsupported=unsupported,
    )
