"""Request and response schemas for the Note endpoints.

Deliberately shaped like :mod:`app.mindmap.schemas` — a note and a mind map are
two renderings of the *same* act: "turn this selection of sources into
something". Keeping the request bodies identical means the frontend reuses one
selection and one composite-key derivation for both.

The key helpers are therefore imported rather than reimplemented.  Both
features must agree on what a selection is called, because the frontend derives
the same key client-side to decide whether a GET will find anything.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.mindmap.schemas import composite_key, split_composite_key

__all__ = ["GenerateRequest", "NoteResponse", "composite_key", "split_composite_key"]


class GenerateRequest(BaseModel):
    """Request body for POST /note/generate.

    The workspace selects sources in its sidebar, so a note can be written from
    one source or from several at once.  ``source_ids`` wins when both are
    supplied; ``source_id`` is retained for the single-source case and for older
    clients.  GitHub repos are prefixed by the loader as ``repo:<owner>/<name>``
    (hence the slash in the id).
    """

    source_ids: list[str] | None = Field(
        default=None,
        description=(
            "The sources to write a combined note from.  One entry behaves "
            "exactly like the single-source case; several entries produce a note "
            "spanning all of them."
        ),
        examples=[["repo:AdnanZamanNiloy/contexforge", "doc:handbook"]],
    )
    source_id: str | None = Field(
        default=None,
        description=("A single source to generate a note from.  Ignored when source_ids is supplied."),
        examples=["repo:AdnanZamanNiloy/PhoneNumIdentify-"],
    )
    refresh: bool = Field(
        default=False,
        description="Regenerate even when a cached note exists for this selection.",
    )

    @field_validator("source_id")
    @classmethod
    def source_id_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("source_id must not be blank or whitespace-only")
        return v.strip()

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_be_meaningful(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [s.strip() for s in v if s and s.strip()]
        return cleaned or None

    @model_validator(mode="after")
    def at_least_one_source(self) -> GenerateRequest:
        if not self.source_ids and not self.source_id:
            raise ValueError("provide source_ids (one or more) or a single source_id")
        return self

    def resolved_source_ids(self) -> list[str]:
        """The effective selection, de-duplicated and order-independent."""
        ids = self.source_ids or ([self.source_id] if self.source_id else [])
        seen: set[str] = set()
        unique: list[str] = []
        for s in ids:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique

    def key(self) -> str:
        return composite_key(self.resolved_source_ids())

    model_config = {"frozen": True}


class NoteResponse(BaseModel):
    """A generated (or previously stored) note for a selection of sources."""

    source_id: str = Field(
        description=(
            "Storage key for this note.  A single source uses its own id; a "
            "multi-source selection uses a sorted composite key."
        )
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Every source that contributed to this note.",
    )
    title: str = Field(description="Title of the note.")
    markdown: str = Field(description="Markdown body, starting with an H1 title and H2 sections.")
    chunk_count: int = Field(ge=0, description="Number of source chunks used.")
    created_at: str | None = Field(default=None, description="ISO-8601 creation timestamp (when persisted).")

    model_config = {"frozen": True}
