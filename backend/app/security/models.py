"""Value types for the Security & Quality scan."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "CODE_CATEGORIES",
    "SEVERITIES",
    "Finding",
    "severity_rank",
    "worst",
]


#: Ordered worst-first.  ``unknown`` is a real outcome, not a rounding of
#: ``low``: an advisory with no severity we can read is not evidence of a
#: problem, and is not evidence of safety either.
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low", "unknown")

#: The categories a code finding can fall into, in the order the report shows
#: them.  Grouped by what the reader has to do about it: what can execute code,
#: what can leak a credential, what weakens a guarantee, what is merely untidy.
CODE_CATEGORIES: tuple[str, ...] = (
    "Code execution",
    "Injection",
    "Secrets",
    "Cryptography",
    "Transport",
    "Deserialization",
    "Memory safety",
)


def severity_rank(severity: str) -> int:
    """Sort key for a severity, worst first."""
    try:
        return SEVERITIES.index(severity)
    except ValueError:
        return len(SEVERITIES)


def worst(severities) -> str:
    """The most serious severity in *severities*, or ``unknown`` when empty."""
    ranked = sorted(severities, key=severity_rank)
    return ranked[0] if ranked else "unknown"


@dataclass
class Finding:
    """One thing worth a reader's attention.

    ``source`` records where the finding came from -- a matched code pattern, a
    secret, a dependency advisory or a repository gate -- because a code pattern
    and a published CVE carry very different weight and a report that blurs them
    is not worth reading.
    """

    id: str
    title: str
    severity: str
    category: str
    detail: str = ""
    #: Where in the repository: a file path, a dependency name, or empty.
    location: str = ""
    line: int | None = None
    #: A link to the advisory, when there is one.
    reference: str = ""
    #: ``code``, ``secret``, ``dependency`` or ``quality``.
    source: str = "code"
    #: How sure the scanner is this is a real problem rather than a pattern that
    #: merely looks like one.  A hit marked ``medium`` is shown, but not counted
    #: as a confirmed issue.
    confidence: str = "high"
    cwe: str = ""
    #: The matched line, truncated, so a reader can judge without opening the file.
    snippet: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "detail": self.detail,
            "location": self.location,
            "line": self.line,
            "reference": self.reference,
            "source": self.source,
            "confidence": self.confidence,
            "cwe": self.cwe,
            "snippet": self.snippet,
            **({"extra": self.extra} if self.extra else {}),
        }
