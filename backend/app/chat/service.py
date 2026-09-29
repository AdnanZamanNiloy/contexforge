"""Chat service — session/message CRUD scoped to a project.

The store owns persistence; this service enforces the two rules that give chat
history its guarantees:

- a session can only exist under a real project (validated against
  ``ProjectsStore``), so a typo'd project id can never create orphan history;
- message history is append-only.  Existing messages are never rewritten
  because a source was deleted or the workspace selection changed — only the
  message being streamed is patched, and only with its own result.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .store import ChatStore

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from app.projects.store import ProjectsStore

__all__ = ["ChatService"]

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, store: ChatStore, projects: ProjectsStore) -> None:
        self._store = store
        self._projects = projects

    async def _project_exists(self, project_id: str) -> bool:
        return await self._projects.get_project(project_id) is not None

    # -- sessions ------------------------------------------------------

    async def list_sessions(self, project_id: str) -> list[dict[str, Any]] | None:
        if not await self._project_exists(project_id):
            return None
        return await self._store.list_sessions(project_id)

    async def create_session(self, project_id: str, title: str = "") -> dict[str, Any] | None:
        if not await self._project_exists(project_id):
            return None
        return await self._store.create_session(project_id, title)

    async def get_session(self, session_id: str, with_messages: bool = True) -> dict[str, Any] | None:
        session = await self._store.get_session(session_id)
        if not session:
            return None
        if with_messages:
            session["messages"] = await self._store.list_messages(session_id)
        return session

    async def rename_session(self, session_id: str, title: str) -> dict[str, Any] | None:
        return await self._store.rename_session(session_id, title)

    async def delete_session(self, session_id: str) -> bool:
        return await self._store.delete_session(session_id)

    async def delete_for_project(self, project_id: str) -> int:
        """Drop every session + message for a project (used on project delete)."""
        return await self._store.clear_project_sessions(project_id)

    # -- messages ------------------------------------------------------

    async def list_messages(self, session_id: str) -> list[dict[str, Any]] | None:
        if not await self._store.get_session(session_id):
            return None
        return await self._store.list_messages(session_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        source_ids: list[str] | None = None,
        status: str = "done",
        confidence: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._store.add_message(
            session_id=session_id,
            role=role,
            text=text,
            source_ids=source_ids,
            status=status,
            confidence=confidence,
            message_id=message_id,
        )

    async def update_message(self, message_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        return await self._store.update_message(message_id, patch)
