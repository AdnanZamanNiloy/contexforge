"""HTTP routes for persisted chat sessions.

Sessions are created and listed under their project (``/projects/{id}/sessions``)
so ownership is explicit; individual sessions are addressed directly
(``/sessions/{id}``) for reading history, appending messages and deletion.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_chat_service

from .schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatMessageUpdate,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatSessionUpdate,
)
from .service import ChatService

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _session_response(session: dict) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session["id"],
        project_id=session["project_id"],
        title=session.get("title", ""),
        message_count=session.get("message_count", 0),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


async def _require_session(service: ChatService, session_id: str) -> dict:
    session = await service.get_session(session_id, with_messages=False)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat session '{session_id}' not found.")
    return session


@router.get(
    "/projects/{project_id}/sessions",
    response_model=ChatSessionListResponse,
    summary="List a project's chat sessions",
)
async def list_sessions(
    project_id: str,
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionListResponse:
    sessions = await service.list_sessions(project_id)
    if sessions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ChatSessionListResponse(
        sessions=[_session_response(s) for s in sessions],
        total=len(sessions),
    )


@router.post(
    "/projects/{project_id}/sessions",
    response_model=ChatSessionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chat session in a project",
)
async def create_session(
    project_id: str,
    payload: ChatSessionCreate,
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionDetail:
    session = await service.create_session(project_id, payload.title)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project_id}' not found.")
    return ChatSessionDetail(**_session_response(session).model_dump(), messages=[])


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetail,
    summary="Get a chat session with its full message history",
)
async def get_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionDetail:
    session = await service.get_session(session_id, with_messages=True)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat session '{session_id}' not found.")
    return ChatSessionDetail(
        **_session_response(session).model_dump(),
        messages=[ChatMessageResponse(**m) for m in session.get("messages", [])],
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Rename a chat session",
)
async def rename_session(
    session_id: str,
    payload: ChatSessionUpdate,
    service: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    session = await service.rename_session(session_id, payload.title)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat session '{session_id}' not found.")
    return _session_response(session)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session and all its messages",
)
async def delete_session(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> None:
    ok = await service.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat session '{session_id}' not found.")
    return None


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
    summary="List a session's messages (each with its own source selection)",
)
async def list_messages(
    session_id: str,
    service: ChatService = Depends(get_chat_service),
) -> list[ChatMessageResponse]:
    messages = await service.list_messages(session_id)
    if messages is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat session '{session_id}' not found.")
    return [ChatMessageResponse(**m) for m in messages]


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a message to a session",
)
async def add_message(
    session_id: str,
    payload: ChatMessageCreate,
    service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    message = await service.add_message(
        session_id=session_id,
        role=payload.role,
        text=payload.text,
        source_ids=payload.source_ids,
        status=payload.status,
        confidence=payload.confidence,
        message_id=payload.message_id,
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat session '{session_id}' not found.")
    return ChatMessageResponse(**message)


@router.patch(
    "/messages/{message_id}",
    response_model=ChatMessageResponse,
    summary="Update a message (streaming result, status)",
)
async def update_message(
    message_id: str,
    payload: ChatMessageUpdate,
    service: ChatService = Depends(get_chat_service),
) -> ChatMessageResponse:
    message = await service.update_message(message_id, payload.model_dump(exclude_unset=True))
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message '{message_id}' not found.")
    return ChatMessageResponse(**message)
