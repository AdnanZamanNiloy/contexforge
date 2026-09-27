"""Request/response schemas for per-source metadata management."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

__all__ = ["UpdateSourceRequest", "UpdateSourceResponse"]


class UpdateSourceRequest(BaseModel):
    """Body for ``PATCH /ingest/source/{source_id}``.

    A source's title is derived from its chunk metadata; this persists a user
    override on top of it.  Only ``title`` is editable today — the id, type and
    chunk count all belong to the retrieval store.
    """

    title: str = Field(
        ...,
        description="New display name for the source.",
        examples=["Payments service runbook"],
        max_length=200,
    )

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("title must not be blank or whitespace-only")
        return cleaned

    model_config = {"frozen": True}


class UpdateSourceResponse(BaseModel):
    """Confirmation that a source's display title was updated."""

    source_id: str = Field(description="The renamed source.")
    title: str = Field(description="The new display title.")
    updated_at: str = Field(description="ISO-8601 timestamp of the rename.")

    model_config = {"frozen": True}
