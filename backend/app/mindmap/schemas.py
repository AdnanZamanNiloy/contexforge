"""Request and response schemas for the Mind Map endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

__all__ = ["GenerateRequest", "MindMapResponse"]


class GenerateRequest(BaseModel):
    """Request body for POST /mindmap/generate.

    ``source_id`` identifies the ingested source whose full content the map is
    generated from.  Must be non-blank; the loader prefixes GitHub repos as
    ``repo:<owner>/<name>`` (hence the slash in the id).
    """

    source_id: str = Field(
        ...,
        description=(
            "The source to generate a mind map from.  GitHub repos use "
            "'repo:owner/name'."
        ),
        examples=["repo:AdnanZamanNiloy/PhoneNumIdentify-"],
    )

    @field_validator("source_id")
    @classmethod
    def source_id_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_id must not be blank or whitespace-only")
        return v.strip()

    model_config = {"frozen": True}


class MindMapResponse(BaseModel):
    """A generated (or previously stored) mind map for a source."""

    source_id: str = Field(description="The source this map was generated from.")
    title: str = Field(description="Human-readable source title used as the root node.")
    markdown: str = Field(
        description="Markdown list outline rendered by the mind map component."
    )
    chunk_count: int = Field(ge=0, description="Number of source chunks used.")
    created_at: str | None = Field(
        default=None, description="ISO-8601 creation timestamp (when persisted)."
    )

    model_config = {"frozen": True}
