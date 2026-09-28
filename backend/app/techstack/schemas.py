"""Request/response contracts for the Dependency & Tech Stack scan."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["TechStackRequest", "TechStackResponse"]


class TechStackRequest(BaseModel):
    """Scan a project's GitHub source."""

    project_id: str = Field(description="Project whose GitHub source should be scanned.")
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
    """

    repository: str = ""
    summary: str = ""
    languages: list[dict] = Field(default_factory=list)
    frameworks: list[dict] = Field(default_factory=list)
    technologies: list[dict] = Field(default_factory=list)
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
