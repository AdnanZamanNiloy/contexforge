"""
schemas/github.py — Request schema for GitHub repository ingestion.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl

__all__ = ["GithubIngestRequest"]


class GithubIngestRequest(BaseModel):
    """Request body for POST /github/ingest.

    Attributes:
        repo_url: Full HTTPS URL of the public GitHub repository.
        branch:   Branch to clone.  Defaults to the repo's default branch.
    """

    repo_url: str = Field(
        ...,
        description="Full GitHub repository URL (e.g. https://github.com/owner/repo).",
        examples=["https://github.com/anthropics/anthropic-sdk-python"],
    )
    branch: str | None = Field(
        default=None,
        description="Branch name to clone.  Omit to use the repository default branch.",
        examples=["main", "develop"],
    )

    model_config = {"frozen": True}