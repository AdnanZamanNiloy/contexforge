"""SQLite persistence for generated notes.

Stores one row per selection (keyed by ``source_id``, which is the composite
selection key) holding the markdown body written from that selection's chunks.
Follows the ``MindMapStore`` pattern on the storage side — WAL mode, a
short-lived connection per operation, and an idempotent schema.

The table is named ``generated_notes``, not ``notes``, and that is deliberate.
An earlier project-notes feature used ``notes`` in this same database file for
something else entirely (authored, project-scoped notes keyed by ``id`` and
``project_id``).  ``CREATE TABLE IF NOT EXISTS`` is a *no-op* against an existing
table whatever its shape, so reusing the name silently inherited an incompatible
schema and every query failed on a missing ``source_id`` column.  A distinct
name lets the two features share one database file and leaves the old rows
readable.

Keying on the selection key means a note is generated once and reused until the
selection changes or ``refresh`` is passed, so the frontend never regenerates on
every visit.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings
from observability.tracer import observe

__all__ = ["NoteStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS generated_notes (
    source_id   TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'Note',
    markdown    TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class NoteStore:
    """Background-agnostic SQLite store for generated notes."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.NOTES_DIR / "notes.db")

    @observe(name="note_store_get")
    async def get(self, source_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, source_id)

    @observe(name="note_store_upsert")
    async def upsert(
        self,
        source_id: str,
        title: str,
        markdown: str,
        chunk_count: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_sync, source_id, title, markdown, chunk_count)

    @observe(name="note_store_delete")
    async def delete(self, source_id: str) -> None:
        await asyncio.to_thread(self._delete_sync, source_id)

    def close(self) -> None:
        """No persistent connection to close; retained for the common API."""

    # ------------------------------------------------------------------ #
    # Synchronous internals (thread-pool only)
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        return conn

    def _get_sync(self, source_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT source_id, title, markdown, chunk_count, created_at, "
                "updated_at FROM generated_notes WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _upsert_sync(self, source_id: str, title: str, markdown: str, chunk_count: int) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO generated_notes (source_id, title, markdown, chunk_count,
                                       created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        title = excluded.title,
                        markdown = excluded.markdown,
                        chunk_count = excluded.chunk_count,
                        updated_at = excluded.updated_at
                    """,
                    (source_id, title, markdown, chunk_count, now, now),
                )
            return {
                "source_id": source_id,
                "title": title,
                "markdown": markdown,
                "chunk_count": chunk_count,
                "created_at": now,
                "updated_at": now,
            }
        finally:
            conn.close()

    def _delete_sync(self, source_id: str) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute("DELETE FROM generated_notes WHERE source_id = ?", (source_id,))
        finally:
            conn.close()
