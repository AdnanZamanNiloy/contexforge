"""SQLite persistence for chat sessions and their messages.

A chat session belongs to exactly one project and holds an ordered list of
messages.  Each message stores the *exact* source selection that produced it,
so a session's history stays intact even as the workspace selection changes or
sources are deleted — the first message can cite one source while the third
cites all of them, and both remain readable for the life of the project.

Deletion is cascading and enforced in SQL: deleting a project removes its
sessions, and deleting a session removes its messages (including the
per-message source selections stored on them).  Nothing else is ever allowed to
mutate existing message rows — sources come and go, chat history does not.

Follows the existing ``ProjectsStore`` / ``MindMapStore`` pattern: WAL mode, one
short-lived connection per operation, never shared across threads.  Foreign keys
are enabled per connection because SQLite only enforces ``ON DELETE CASCADE``
when ``PRAGMA foreign_keys`` is on.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings

__all__ = ["ChatStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    id         TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'done',
    source_ids TEXT NOT NULL DEFAULT '[]',
    confidence TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_project ON chat_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, seq);
"""

_ROLES = ("user", "assistant", "system")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_ids(values: Any) -> list[str]:
    """Trim, drop blanks and de-duplicate while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        sid = str(raw).strip() if raw is not None else ""
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _loads_source_ids(raw: Any) -> list[str]:
    """Decode a stored source-selection column into a clean list of ids."""
    if isinstance(raw, list):
        return _clean_ids(raw)
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except TypeError, ValueError:
            return []
        return _clean_ids(parsed if isinstance(parsed, list) else [])
    return []


def _loads_json(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except TypeError, ValueError:
        return None


class ChatStore:
    """Background-agnostic SQLite store for chat sessions + messages."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.CHAT_DB_PATH)

    # -- sessions ------------------------------------------------------

    async def list_sessions(self, project_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_sessions_sync, project_id)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_session_sync, session_id)

    async def create_session(self, project_id: str, title: str = "") -> dict[str, Any] | None:
        return await asyncio.to_thread(self._create_session_sync, project_id, title)

    async def rename_session(self, session_id: str, title: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._rename_session_sync, session_id, title)

    async def delete_session(self, session_id: str) -> bool:
        return await asyncio.to_thread(self._delete_session_sync, session_id)

    async def clear_project_sessions(self, project_id: str) -> int:
        """Remove every session (and message) belonging to *project_id*."""
        return await asyncio.to_thread(self._clear_project_sessions_sync, project_id)

    # -- messages ------------------------------------------------------

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_messages_sync, session_id)

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
        return await asyncio.to_thread(
            self._add_message_sync, session_id, role, text, source_ids, status, confidence, message_id
        )

    async def update_message(self, message_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._update_message_sync, message_id, patch)

    def close(self) -> None:
        """No persistent connection; retained for the common close_all API."""

    # -- sync internals: connection ------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # SQLite defaults foreign-key enforcement off; without this the
        # ON DELETE CASCADE below would silently leave orphaned rows behind.
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA)
        conn.commit()
        self._migrate_sync(conn)
        return conn

    @staticmethod
    def _migrate_sync(conn: sqlite3.Connection) -> None:
        """Add the monotonic ``seq`` ordering column to pre-existing databases.

        Messages used to be ordered by ``created_at`` with ``rowid`` as a
        tie-break, but the user and assistant rows of one turn are written by
        two concurrent requests: the assistant placeholder could be inserted
        first and both timestamps differ by microseconds, so history could load
        assistant-before-user.  ``seq`` is a strictly increasing insertion
        counter that makes order deterministic.  ``ALTER TABLE`` cannot add an
        AUTOINCREMENT column, so legacy tables are rebuilt with rows copied in
        their best-known order.
        """
        info = conn.execute("PRAGMA table_info(chat_messages)").fetchall()
        if not info:
            return
        # The expected shape has ``seq`` as the INTEGER PRIMARY KEY (autoincrement).
        # A column merely *named* seq (e.g. a nullable add from an older attempt)
        # is not enough — it would never auto-assign, so ordering would stay
        # broken. Check the primary-key flag, not just the column name.
        seq_row = next((row for row in info if row[1] == "seq"), None)
        seq_is_pk = seq_row is not None and seq_row[5] == 1
        if seq_is_pk:
            return
        logger.info("chat: migrating chat_messages onto monotonic seq ordering")
        with conn:
            conn.execute("ALTER TABLE chat_messages RENAME TO chat_messages_legacy")
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT INTO chat_messages"
                " (id, session_id, role, text, status, source_ids, confidence, created_at)"
                " SELECT id, session_id, role, text, status, source_ids, confidence, created_at"
                " FROM chat_messages_legacy ORDER BY created_at ASC, rowid ASC"
            )
            conn.execute("DROP TABLE chat_messages_legacy")
        conn.commit()

    # -- sync internals: sessions --------------------------------------

    def _session_row(self, row: sqlite3.Row, message_count: int | None = None) -> dict[str, Any]:
        data = dict(row)
        if message_count is not None:
            data["message_count"] = message_count
        return data

    def _message_count(self, conn: sqlite3.Connection, session_id: str) -> int:
        row = conn.execute("SELECT COUNT(*) AS n FROM chat_messages WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["n"]) if row else 0

    def _list_sessions_sync(self, project_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM chat_sessions WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
            return [self._session_row(r, self._message_count(conn, r["id"])) for r in rows]
        finally:
            conn.close()

    def _get_session_sync(self, session_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return None
            return self._session_row(row, self._message_count(conn, session_id))
        finally:
            conn.close()

    def _create_session_sync(self, project_id: str, title: str) -> dict[str, Any] | None:
        session_id = f"chat_{uuid.uuid4().hex[:12]}"
        now = _now()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO chat_sessions (id, project_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, project_id, title or "", now, now),
                )
            return {
                "id": session_id,
                "project_id": project_id,
                "title": title or "",
                "message_count": 0,
                "created_at": now,
                "updated_at": now,
            }
        finally:
            conn.close()

    def _rename_session_sync(self, session_id: str, title: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (title or "", _now(), session_id),
                )
                if cur.rowcount == 0:
                    return None
            return self._get_session_sync(session_id)
        finally:
            conn.close()

    def _delete_session_sync(self, session_id: str) -> bool:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
                # Explicit even though the FK cascade covers it: keeps the
                # operation correct on databases created before foreign_keys
                # enforcement was enabled.
                conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
                return cur.rowcount > 0
        finally:
            conn.close()

    def _clear_project_sessions_sync(self, project_id: str) -> int:
        conn = self._connect()
        try:
            with conn:
                ids = [
                    r["id"]
                    for r in conn.execute("SELECT id FROM chat_sessions WHERE project_id = ?", (project_id,)).fetchall()
                ]
                if not ids:
                    return 0
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM chat_messages WHERE session_id IN ({placeholders})", ids)
                cur = conn.execute("DELETE FROM chat_sessions WHERE project_id = ?", (project_id,))
                return cur.rowcount
        finally:
            conn.close()

    # -- sync internals: messages --------------------------------------

    def _message_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["source_ids"] = _loads_source_ids(data.get("source_ids"))
        data["confidence"] = _loads_json(data.get("confidence"))
        return data

    def _list_messages_sync(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            # Ordered by the monotonic insertion counter, never by timestamp:
            # the two rows of a turn are written by separate requests and can
            # share/out-of-order timestamps, but ``seq`` always reflects the
            # order they were inserted.
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            ).fetchall()
            return [self._message_row(r) for r in rows]
        finally:
            conn.close()

    def _add_message_sync(
        self,
        session_id: str,
        role: str,
        text: str,
        source_ids: list[str] | None,
        status: str,
        confidence: dict[str, Any] | None,
        message_id: str | None,
    ) -> dict[str, Any] | None:
        role = role if role in _ROLES else "user"
        now = _now()
        conn = self._connect()
        try:
            exists = conn.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if not exists:
                return None
            mid = message_id or f"msg_{uuid.uuid4().hex[:12]}"
            ids = _clean_ids(source_ids)
            with conn:
                conn.execute(
                    "INSERT INTO chat_messages"
                    " (id, session_id, role, text, status, source_ids, confidence, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        mid,
                        session_id,
                        role,
                        text or "",
                        status or "done",
                        json.dumps(ids),
                        json.dumps(confidence) if confidence is not None else None,
                        now,
                    ),
                )
                conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            return {
                "id": mid,
                "session_id": session_id,
                "role": role,
                "text": text or "",
                "status": status or "done",
                "source_ids": ids,
                "confidence": confidence,
                "created_at": now,
            }
        finally:
            conn.close()

    def _update_message_sync(self, message_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed: dict[str, Any] = {}
        if "text" in patch and patch["text"] is not None:
            allowed["text"] = patch["text"]
        if "status" in patch and patch["status"] is not None:
            allowed["status"] = patch["status"]
        if "source_ids" in patch and patch["source_ids"] is not None:
            allowed["source_ids"] = json.dumps(_clean_ids(patch["source_ids"]))
        if "confidence" in patch:
            allowed["confidence"] = json.dumps(patch["confidence"]) if patch["confidence"] is not None else None
        conn = self._connect()
        try:
            if not allowed:
                row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
                return self._message_row(row) if row is not None else None
            columns = ", ".join(f"{k} = ?" for k in allowed)
            with conn:
                cur = conn.execute(
                    f"UPDATE chat_messages SET {columns} WHERE id = ?",
                    [*allowed.values(), message_id],
                )
                if cur.rowcount == 0:
                    return None
                row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
                if row is not None:
                    conn.execute(
                        "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                        (_now(), row["session_id"]),
                    )
            return self._message_row(row) if row is not None else None
        finally:
            conn.close()
