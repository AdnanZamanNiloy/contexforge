"""Request/response schemas for per-source metadata management."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "SourceContentResponse",
    "SourceDetailResponse",
    "UpdateSourceRequest",
    "UpdateSourceResponse",
]


class SourceChunkOut(BaseModel):
    """One indexed chunk of a source, exactly as retrieval sees it.

    Exposing the stored text is the point of this payload: a user who uploaded
    a document can confirm what was actually extracted and indexed rather than
    taking the answer's citations on trust.
    """

    chunk_id: str = Field(description="Stable id of the indexed chunk.")
    chunk_index: int | None = Field(
        default=None,
        ge=0,
        description="Position of the chunk in the source, when the loader recorded one.",
    )
    path: str | None = Field(
        default=None,
        description="Source file path, for sources built from many files (a repository).",
    )
    text: str = Field(description="The indexed text of this chunk.")

    model_config = {"frozen": True}


class SourceContentResponse(BaseModel):
    """Response body for ``GET /ingest/source/{id}/content``."""

    source_id: str
    chunks: list[SourceChunkOut] = Field(default_factory=list)
    chunk_count: int = Field(ge=0, description="Number of chunks returned.")
    total_chunks: int = Field(
        ge=0,
        description="Chunks held for this source, which can exceed ``chunk_count``.",
    )
    truncated: bool = Field(
        default=False,
        description="True when chunks were omitted to respect the response cap.",
    )

    model_config = {"frozen": True}


class SourceDetailResponse(BaseModel):
    """Response body for ``GET /ingest/source/{id}``.

    Everything the workspace knows about one source: how it was labelled, where
    it came from, what the loader extracted, and what made it into the index.
    The point is legibility — a user can see that a scanned PDF extracted no
    text, or that a document is far shorter than the file they uploaded.
    """

    source_id: str
    title: str = Field(description="Display title, including any user rename.")
    derived_title: str = Field(
        description="Title derived from chunk metadata, before any rename.",
    )
    renamed: bool = Field(
        default=False,
        description="True when the display title comes from a user rename.",
    )
    source_type: str = Field(
        default="unknown",
        description="Origin format: web, pdf, docx, github, youtube or text.",
    )
    url: str | None = Field(default=None, description="Canonical URL, when the source has one.")
    chunk_count: int = Field(ge=0)
    char_count: int = Field(
        ge=0,
        description="Summed length of the indexed text for this source.",
    )
    language: str | None = Field(default=None, description="Detected language, when known.")
    file_paths: list[str] = Field(
        default_factory=list,
        description="Indexed file paths, for sources built from many files.",
    )
    page_count: int | None = Field(
        default=None,
        description="Pages seen by the PDF loader, for document sources.",
    )
    non_empty_pages: int | None = Field(
        default=None,
        description="Of those pages, how many carried extractable text.",
    )
    is_scanned: bool | None = Field(
        default=None,
        description="True when the PDF loader found no extractable text layer.",
    )
    keywords: list[str] = Field(default_factory=list)
    named_entities: list[dict] = Field(default_factory=list)
    file_available: bool = Field(
        default=False,
        description=(
            "Whether the original upload is retrievable. ContextForge indexes "
            "uploads without retaining the original bytes, so this is false for "
            "document sources."
        ),
    )

    model_config = {"frozen": True}


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
