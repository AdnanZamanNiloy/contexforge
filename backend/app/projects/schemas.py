"""Pydantic schemas for the Projects library API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "AttachSourceRequest",
    "ProjectCreate",
    "ProjectListResponse",
    "ProjectResponse",
    "ProjectUpdate",
    "SetToolSourceRequest",
    "SourceCategory",
]

# Which kinds of sources a project accepts.  The workspace ingest modal is
# scoped to this choice.  "all" is never offered in the UI — it only marks
# projects created before scoping existed so they keep every ingest option.
SourceCategory = Literal["documents", "youtube", "github", "all"]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=80)
    source_category: SourceCategory = Field(default="documents")

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Project name must not be blank.")
        return v.strip()

    @field_validator("description", "category")
    @classmethod
    def strip_optional(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    source_category: SourceCategory | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Project name must not be blank.")
        return v.strip() if isinstance(v, str) else v


class AttachSourceRequest(BaseModel):
    source_id: str = Field(..., min_length=1)

    @field_validator("source_id")
    @classmethod
    def id_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_id must not be blank.")
        return v.strip()


class SetToolSourceRequest(BaseModel):
    """Which source the Studio analysis tools are scoped to."""

    source_id: str = Field(default="", max_length=512)

    @field_validator("source_id")
    @classmethod
    def strip_value(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = ""
    cover: str = "aurora"
    source_category: str = "documents"
    # Studio tools (Architecture, Security, Tech Stack, Health) target one
    # source; the project remembers the last one the user picked.
    tool_source_id: str = ""
    source_ids: list[str] = Field(default_factory=list)
    source_count: int = 0
    # Per-type breakdown + recency helpers for the library UI.  Populated from
    # the live FAISS source inventory so deleted sources never inflate counts.
    source_types: dict[str, int] = Field(default_factory=dict)
    last_source_at: str | None = None
    created_at: str
    updated_at: str
    last_opened_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse] = Field(default_factory=list)
    total: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)
