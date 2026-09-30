"""Request and response schemas for the Mind Map endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = ["GenerateRequest", "MindMapResponse", "composite_key", "split_composite_key"]

MULTI_PREFIX = "multi:"


def composite_key(source_ids: list[str]) -> str:
    """Return the storage/cache key for a set of source ids.

    A single source keeps its own id as the key so every mind map generated
    before multi-source support stays addressable.  Two or more sources get a
    sorted, prefixed key so the same selection always maps to one cache entry
    regardless of the order the user picked them in.
    """
    ids = [s.strip() for s in source_ids if s and s.strip()]
    if not ids:
        raise ValueError("at least one source id is required")
    if len(ids) == 1:
        return ids[0]
    return MULTI_PREFIX + ",".join(sorted(set(ids)))


def split_composite_key(key: str) -> list[str]:
    """Inverse of :func:`composite_key` — recover the source ids from a key."""
    if key.startswith(MULTI_PREFIX):
        return [s for s in key[len(MULTI_PREFIX) :].split(",") if s]
    return [key]


class GenerateRequest(BaseModel):
    """Request body for POST /mindmap/generate.

    The project workspace selects sources in its sidebar, so a map can be built
    from one source or from several at once.  ``source_ids`` wins when both are
    supplied; ``source_id`` is retained for the single-source case and for
    older clients.  GitHub repos are prefixed by the loader as
    ``repo:<owner>/<name>`` (hence the slash in the id).
    """

    source_ids: list[str] | None = Field(
        default=None,
        description=(
            "The sources to build a combined mind map from.  One entry behaves "
            "exactly like the single-source case; several entries produce a map "
            "spanning all of them."
        ),
        examples=[["repo:AdnanZamanNiloy/contexforge", "doc:handbook"]],
    )
    source_id: str | None = Field(
        default=None,
        description=("A single source to generate a mind map from.  Ignored when source_ids is supplied."),
        examples=["repo:AdnanZamanNiloy/PhoneNumIdentify-"],
    )
    refresh: bool = Field(
        default=False,
        description="Regenerate even when a cached map exists for this selection.",
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


class MindMapResponse(BaseModel):
    """A generated (or previously stored) mind map for a selection of sources."""

    source_id: str = Field(
        description=(
            "Storage key for this map.  A single source uses its own id; a "
            "multi-source selection uses a sorted composite key."
        )
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Every source that contributed to this map.",
    )
    title: str = Field(description="Human-readable title used as the root node.")
    markdown: str = Field(description="Markdown list outline rendered by the mind map component.")
    chunk_count: int = Field(ge=0, description="Number of source chunks used.")
    created_at: str | None = Field(default=None, description="ISO-8601 creation timestamp (when persisted).")

    model_config = {"frozen": True}
