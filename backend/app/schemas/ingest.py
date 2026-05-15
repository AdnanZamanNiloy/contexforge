"""
schemas/ingest.py — Request and response schemas for ingestion endpoints.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = ["IngestRequest", "IngestResponse"]

# FIX #4 — simple URL prefix check; full RFC validation done by the loader
_URL_SCHEMES = ("http://", "https://")
_GITHUB_PREFIX = "https://github.com/"


class IngestRequest(BaseModel):
    """Request body for POST /ingest/source.

    Attributes:
        source_type: Origin format of the content.
        source:      URL, repo URL, or raw text depending on ``source_type``.
        metadata:    Optional caller-supplied metadata attached to all chunks.
    """

    source_type: Literal["pdf", "docx", "web", "github", "text"]
    source: str = Field(
        ...,
        min_length=1,
        description="URL, GitHub repo URL, or raw text depending on source_type.",
        examples=["https://example.com/doc", "https://github.com/owner/repo"],
    )
    # FIX #5 — Any values so int/bool metadata from loaders is not rejected
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional key-value metadata attached to every ingested chunk.",
    )

    # FIX #4 — validate source format against source_type at schema level
    @model_validator(mode="after")
    def validate_source_for_type(self) -> "IngestRequest":
        src = self.source.strip()
        st = self.source_type

        if st in {"web"}:
            if not any(src.startswith(scheme) for scheme in _URL_SCHEMES):
                raise ValueError(
                    f"source_type='web' requires an http/https URL, got: '{src}'"
                )

        if st == "github":
            if not src.startswith(_GITHUB_PREFIX):
                raise ValueError(
                    f"source_type='github' requires a URL starting with "
                    f"'{_GITHUB_PREFIX}', got: '{src}'"
                )

        if st == "text":
            if not src.strip():
                raise ValueError("source_type='text' requires non-blank text content")

        return self

    @field_validator("source")
    @classmethod
    def source_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source must not be blank or whitespace-only")
        return v.strip()

    model_config = {"frozen": True}


class IngestResponse(BaseModel):
    """Response body for all ingestion endpoints.

    FIX #6 — adds a human-readable ``message`` field so the client gets
    a clear confirmation without parsing ``chunks_indexed`` themselves.
    """

    source_id: str = Field(description="Unique ID assigned to the ingested source.")
    chunks_indexed: int = Field(
        description="Number of text chunks stored in FAISS and BM25.",
        ge=0,
    )
    message: str = Field(
        description="Human-readable ingestion summary.",
    )

    # FIX #6 — auto-generate message if not supplied
    @model_validator(mode="before")
    @classmethod
    def set_default_message(cls, values: dict) -> dict:
        if "message" not in values or not values.get("message"):
            n = values.get("chunks_indexed", 0)
            sid = values.get("source_id", "")
            values["message"] = (
                f"Successfully indexed {n} chunk{'s' if n != 1 else ''} "
                f"from source '{sid}'."
            )
        return values

    model_config = {"frozen": True}