"""Request/response contracts for the Dependency & Tech Stack scan."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["TechStackRequest", "TechStackResponse"]


class TechStackRequest(BaseModel):
    """Scan one of a project's sources."""

    project_id: str = Field(description="Project whose source should be scanned.")
    source_id: str = Field(
        default="",
        description=(
            "Source to scan.  Blank falls back to the project's remembered selection, then its first GitHub source."
        ),
    )
    refresh: bool = Field(
        default=False,
        description="Ignore the cache and rescan from scratch.",
    )


class TechStackResponse(BaseModel):
    """The scan result.

    Dependencies are grouped by package manager rather than returned flat, since
    that is how a reader thinks about them: "my Go modules" and "my npm dev
    tooling" are different questions.  ``managers`` carries that grouping, and
    ``technologies`` is the recognised-software list the summary is written from.

    ``graph`` is the service graph: a tree of services with the databases,
    platforms and providers they connect to.  It is the part that says how a
    repository is put together, where a flat technology list cannot.
    """

    source_id: str = ""
    repository: str = ""
    summary: str = ""
    languages: list[dict] = Field(default_factory=list)
    frameworks: list[dict] = Field(default_factory=list)
    technologies: list[dict] = Field(default_factory=list)
    graph: dict = Field(default_factory=dict)
    package_managers: list[dict] = Field(default_factory=list)
    dependencies: list[dict] = Field(default_factory=list)
    manifests: list[dict] = Field(default_factory=list)
    skipped: int = 0
    manifest_count: int = 0
    dependency_count: int = 0
    language_count: int = 0
    fingerprint: str = ""
    cached: bool = False
    elapsed_ms: int = 0
    truncated: bool = False
    created_at: str | None = None
