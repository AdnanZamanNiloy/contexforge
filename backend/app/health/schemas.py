"""Request/response contracts for the Health Score & Hotspots scan."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["HealthRequest", "HealthResponse"]


class HealthRequest(BaseModel):
    """Scan one of a project's sources for structural risk."""

    project_id: str = Field(description="Project whose source should be analysed.")
    source_id: str = Field(
        default="",
        description=(
            "Source to analyse.  Blank falls back to the project's remembered selection, then its first GitHub source."
        ),
    )
    refresh: bool = Field(default=False, description="Ignore the cache and rescan from scratch.")


class HealthResponse(BaseModel):
    """The scan result.

    ``hotspots`` is a ranking of individual symbols; ``files`` aggregates the
    worst symbol per file.  ``health`` is a 0-100 summary of the structural-risk
    axis only — see :func:`app.health.risk.health_from_bands` for why it is not
    a composite of several signals.
    """

    source_id: str = ""
    repository: str = ""
    #: ``None`` when nothing could be measured — a repository that was never
    #: analysed is not a healthy one, and a 100 would read as a clean bill.
    health: int | None = None
    band: str = "low"
    summary: str = ""
    #: Raw metrics plus the transformed components and the LRS, so a reader can
    #: reproduce the score by hand.
    weights: dict[str, float] = Field(default_factory=dict)
    band_counts: dict[str, int] = Field(default_factory=dict)
    hotspots: list[dict] = Field(default_factory=list)
    files: list[dict] = Field(default_factory=list)
    largest_files: list[dict] = Field(default_factory=list)
    symbol_count: int = 0
    file_count: int = 0
    measured_languages: list[str] = Field(default_factory=list)
    measured_files: int = 0
    unparsed_files: int = 0
    fetched_files: int = 0
    coverage_note: str = ""
    fingerprint: str = ""
    cached: bool = False
    elapsed_ms: int = 0
    created_at: str | None = None
