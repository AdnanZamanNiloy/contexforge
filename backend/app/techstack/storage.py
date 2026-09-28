"""SQLite persistence for Dependency & Tech Stack scans.

One row per ``(project_id, fingerprint)``, mirroring
:mod:`app.architecture.storage`.  The fingerprint is a digest of the
repository's indexed file set, so it stands in for a commit SHA: re-ingesting an
unchanged repository reuses the row, and any change to the file set invalidates
it — with no extra request to read a SHA the loader never recorded.

The structured result is stored as JSON so a new field can be added to the
report without a migration, and the columns that are queried or sorted on
(language/dependency counts) are promoted to real columns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings
from observability.tracer import observe

__all__ = ["TechStackStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tech_stack (
    project_id        TEXT NOT NULL,
    fingerprint       TEXT NOT NULL,
    repository        TEXT NOT NULL DEFAULT '',
    payload           TEXT NOT NULL,
    manifest_count    INTEGER NOT NULL DEFAULT 0,
    dependency_count  INTEGER NOT NULL DEFAULT 0,
    language_count    INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    PRIMARY KEY (project_id, fingerprint)
);
"""


class TechStackStore:
    """Background-agnostic SQLite store for tech stack scans."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.TECH_STACK_DB_PATH)

    @observe(name="techstack_store_get")
    async def get(self, project_id: str, fingerprint: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, project_id, fingerprint)

    @observe(name="techstack_store_latest")
    async def latest(self, project_id: str) -> dict[str, Any] | None:
        """Most recent scan for a project, whatever its fingerprint."""
        return await asyncio.to_thread(self._latest_sync, project_id)

    @observe(name="techstack_store_upsert")
    async def upsert(self, project_id: str, payload: dict[str, Any], fingerprint: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_sync, project_id, payload, fingerprint)

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

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:  # pragma: no cover - corrupt row
            logger.warning("techstack: unreadable payload for project %s", row["project_id"])
            payload = {}
        payload.setdefault("repository", row["repository"])
        payload.setdefault("fingerprint", row["fingerprint"])
        payload.setdefault("created_at", row["created_at"])
        return payload

    def _get_sync(self, project_id: str, fingerprint: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tech_stack WHERE project_id = ? AND fingerprint = ?",
                (project_id, fingerprint),
            ).fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def _latest_sync(self, project_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM tech_stack WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def _upsert_sync(self, project_id: str, payload: dict[str, Any], fingerprint: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO tech_stack (
                        project_id, fingerprint, repository, payload, manifest_count,
                        dependency_count, language_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, fingerprint) DO UPDATE SET
                        repository = excluded.repository,
                        payload = excluded.payload,
                        manifest_count = excluded.manifest_count,
                        dependency_count = excluded.dependency_count,
                        language_count = excluded.language_count,
                        created_at = excluded.created_at
                    """,
                    (
                        project_id,
                        fingerprint,
                        payload.get("repository") or "",
                        json.dumps(payload),
                        int(payload.get("manifest_count") or 0),
                        int(payload.get("dependency_count") or 0),
                        int(payload.get("language_count") or 0),
                        now,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM tech_stack WHERE project_id = ? AND fingerprint = ?",
                (project_id, fingerprint),
            ).fetchone()
            return self._row_to_record(row)
        finally:
            conn.close()
