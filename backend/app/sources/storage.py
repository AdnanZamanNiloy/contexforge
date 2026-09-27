"""SQLite persistence for per-source metadata overrides.

A source's display title is *derived* from its chunk metadata (repo name,
filename, ingest title) and lives in FAISS/BM25 alongside the chunks.  Letting a
user rename a source therefore needs somewhere to record a custom name without
rewriting every chunk row in both retrieval stores.

This store keeps only that override: ``source_id → title``.  ``GET /ingest/sources``
layers it over the derived title, so renaming is a single-row upsert that
survives a restart and costs nothing at query time.  Re-ingesting a source
deletes its override, because the derived title is authoritative again.

Follows the existing ``ProjectsStore`` / ``MindMapStore`` pattern: WAL mode, one
short-lived connection per operation, never shared across threads.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.config.settings import settings

__all__ = ["SourceMetaStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_overrides (
    source_id  TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SourceMetaStore:
    """Persisted per-source metadata overrides (currently the display title)."""

    def __init__(self, db_path=None) -> None:
        self._db_path = db_path or settings.SOURCE_META_DB_PATH
        self._initialised = False
        self._init_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_sync(self) -> None:
        if self._initialised:
            return
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        self._initialised = True

    async def _ensure_initialised(self) -> None:
        if self._initialised:
            return
        async with self._init_lock:
            await asyncio.to_thread(self._init_sync)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def _all_sync(self) -> dict[str, str]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT source_id, title FROM source_overrides").fetchall()
        except sqlite3.OperationalError as exc:  # pragma: no cover - defensive
            logger.warning("source meta: read failed (%s) — using derived titles.", exc)
            return {}
        finally:
            conn.close()
        return {row["source_id"]: row["title"] for row in rows if row["title"]}

    async def all_titles(self) -> dict[str, str]:
        """Every stored override as ``{source_id: title}``.

        Returns an empty mapping on any storage failure so a read error degrades
        to the derived titles rather than breaking the source list.
        """
        await self._ensure_initialised()
        return await asyncio.to_thread(self._all_sync)

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    def _set_title_sync(self, source_id: str, title: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            now = _now()
            conn.execute(
                """
                INSERT INTO source_overrides (source_id, title, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (source_id, title, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {"source_id": source_id, "title": title, "updated_at": now}

    async def set_title(self, source_id: str, title: str) -> dict[str, Any]:
        """Persist a custom display title for *source_id*."""
        await self._ensure_initialised()
        return await asyncio.to_thread(self._set_title_sync, source_id, title)

    def _clear_sync(self, source_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM source_overrides WHERE source_id = ?", (source_id,))
            conn.commit()
        finally:
            conn.close()

    async def clear(self, source_id: str) -> None:
        """Drop the override for *source_id* so the derived title applies again."""
        await self._ensure_initialised()
        await asyncio.to_thread(self._clear_sync, source_id)

    def _clear_all_sync(self) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM source_overrides")
            conn.commit()
        finally:
            conn.close()

    async def clear_all(self) -> None:
        """Drop every override — used when the whole knowledge base is cleared."""
        await self._ensure_initialised()
        await asyncio.to_thread(self._clear_all_sync)
