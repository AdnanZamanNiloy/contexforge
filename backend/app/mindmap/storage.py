"""SQLite persistence for generated mind maps.

Stores one row per source (keyed by ``source_id``) holding the markdown
outline produced from that source's chunks.  SQLite matches the existing
``BM25Index`` / ``RepositoryStore`` pattern (WAL mode).  Keying on ``source_id``
means a map is generated once and reused until the source is deleted — the
frontend never has to regenerate on every visit.

Each operation opens its own connection (``check_same_thread=False``); WAL
coordinates concurrent reads/writes so a single connection is never shared
across threads.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import settings
from observability.tracer import observe

__all__ = ["MindMapStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mindmaps (
    source_id   TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'Mind Map',
    markdown    TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class MindMapStore:
    """Background-agnostic SQLite store for generated mind maps."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.MINDMAP_DIR / "mindmaps.db")

    @observe(name="mindmap_store_get")
    async def get(self, source_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, source_id)

    @observe(name="mindmap_store_upsert")
    async def upsert(
        self,
        source_id: str,
        title: str,
        markdown: str,
        chunk_count: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._upsert_sync, source_id, title, markdown, chunk_count
        )

    @observe(name="mindmap_store_delete")
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
                "SELECT source_id, title, markdown, chunk_count, created_at, updated_at "
                "FROM mindmaps WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _upsert_sync(
        self, source_id: str, title: str, markdown: str, chunk_count: int
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO mindmaps (source_id, title, markdown, chunk_count,
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
                conn.execute("DELETE FROM mindmaps WHERE source_id = ?", (source_id,))
        finally:
            conn.close()
