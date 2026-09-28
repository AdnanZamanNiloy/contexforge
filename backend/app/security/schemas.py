"""Request and response contracts for the Security & Quality scan."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["SecurityRequest", "SecurityResponse"]


class SecurityRequest(BaseModel):
    """Scan a project's GitHub source."""

    project_id: str = Field(description="Project whose GitHub source should be scanned.")
    refresh: bool = Field(
        default=False,
        description="Ignore the cache and rescan from scratch.",
    )


class SecurityResponse(BaseModel):
    """The scan result.

    ``findings`` is the flat, worst-first list.  ``code``, ``dependencies`` and
    ``quality`` are the three evidence sources kept apart, because a code
    pattern, a published advisory and a missing CI workflow do not carry the
    same weight and a reader needs to tell them apart at a glance.

    ``limitations`` is part of the contract, not a footnote.  This scan does not
    trace data across files, and a report that implied otherwise would be trusted
    for exactly the cases it cannot see.
    """

    repository: str = ""
    summary: str = ""
    findings: list[dict] = Field(default_factory=list)
    finding_count: int = 0
    counts: dict = Field(default_factory=dict)
    worst_severity: str = "unknown"
    by_category: list[dict] = Field(default_factory=list)
    code: dict = Field(default_factory=dict)
    dependencies: dict = Field(default_factory=dict)
    quality: list[dict] = Field(default_factory=list)
    gate_count: int = 0
    limitations: list[str] = Field(default_factory=list)
    truncated: bool = False
    fingerprint: str = ""
    cached: bool = False
    elapsed_ms: int = 0
    created_at: str | None = None
