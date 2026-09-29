"""Request/response contracts for the Architecture Diagram.

Deliberately thin: the graph itself is not echoed back as a nested structure.
The client renders ``mermaid``, and re-deriving nodes from Mermaid on the client
would just be a second parser to keep in sync.  The counts are exposed so the UI
can show "12 components · 15 connections" without parsing anything.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "ArchitectureGenerateRequest",
    "ArchitecturePayload",
    "ArchitectureResponse",
]


class ArchitectureGenerateRequest(BaseModel):
    """Generate a diagram for one of a project's sources."""

    project_id: str = Field(description="Project whose source should be mapped.")
    source_id: str = Field(
        default="",
        description=(
            "Source to map.  Blank falls back to the project's remembered selection, then its first GitHub source."
        ),
    )
    refresh: bool = Field(
        default=False,
        description="Ignore the cache and regenerate from scratch.",
    )


class ArchitecturePayload(BaseModel):
    """One SSE frame carrying the finished diagram."""

    source_id: str = ""
    mermaid: str
    explanation: str
    node_count: int
    edge_count: int
    group_count: int
    repository: str
    branch: str
    fingerprint: str
    cached: bool
    elapsed_ms: int
    truncated_paths: int = 0


class ArchitectureResponse(ArchitecturePayload):
    """A cached diagram, returned by GET and by the SSE stream's final frame."""

    model_config = {"frozen": True}


ArchitectureEvent = Literal["diagram", "error"]
