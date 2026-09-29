"""Pydantic schemas for the persisted chat API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "ChatMessageCreate",
    "ChatMessageResponse",
    "ChatMessageUpdate",
    "ChatSessionCreate",
    "ChatSessionDetail",
    "ChatSessionListResponse",
    "ChatSessionResponse",
    "ChatSessionUpdate",
    "MessageRole",
]

MessageRole = Literal["user", "assistant", "system"]


def _clean_ids(values: list[str] | None) -> list[str]:
    """Drop blanks/duplicates but otherwise preserve the caller's ordering.

    The selection is stored verbatim (order included) because it records what
    the user actually had selected when the message was sent; only noise is
    removed so an all-blank list becomes an empty, unscoped selection.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in values or []:
        sid = str(raw).strip() if raw is not None else ""
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


class ChatSessionCreate(BaseModel):
    title: str = Field(default="", max_length=200)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else ""


class ChatSessionUpdate(BaseModel):
    title: str = Field(..., max_length=200)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else ""


class ChatMessageCreate(BaseModel):
    role: MessageRole = Field(default="user")
    text: str = Field(default="", max_length=100000)
    status: str = Field(default="done", max_length=32)
    # The exact source selection used for this message.  Persisted per message
    # so history never changes when the workspace selection later changes.
    source_ids: list[str] = Field(default_factory=list)
    confidence: dict[str, Any] | None = None
    # Optional client-supplied id.  Lets the UI keep its optimistic message id
    # and the persisted row aligned instead of reconciling them afterwards.
    message_id: str | None = Field(default=None, max_length=128)

    @field_validator("source_ids")
    @classmethod
    def clean_source_ids(cls, v: list[str]) -> list[str]:
        return _clean_ids(v)


class ChatMessageUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=100000)
    status: str | None = Field(default=None, max_length=32)
    source_ids: list[str] | None = None
    confidence: dict[str, Any] | None = None

    @field_validator("source_ids")
    @classmethod
    def clean_source_ids(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_ids(v)


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    text: str = ""
    status: str = "done"
    source_ids: list[str] = Field(default_factory=list)
    confidence: dict[str, Any] | None = None
    created_at: str


class ChatSessionResponse(BaseModel):
    id: str
    project_id: str
    title: str = ""
    message_count: int = 0
    created_at: str
    updated_at: str


class ChatSessionDetail(ChatSessionResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionResponse] = Field(default_factory=list)
    total: int = 0
