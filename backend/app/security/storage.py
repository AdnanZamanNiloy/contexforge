"""SQLite cache for security scans.

Same shape as the tech stack store: one row per project holding the finished
payload as JSON, keyed by a fingerprint of the indexed file paths.  A GitHub
loader never records a commit SHA, so the fingerprint is the honest equivalent --
the same file list means the same scan.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from observability.tracer import observe

__all__ = ["SecurityStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_scans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT    NOT NULL,
    repository  TEXT    NOT NULL DEFAULT '',
    fingerprint TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    UNIQUE (project_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_security_project
    ON security_scans (project_id, created_at DESC);
"""


class SecurityStore:
    """Persists the most recent scan per project and fingerprint."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = Path(db_path) if db_path else Path("data/security.db")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @observe(name="security_store_get")
    async def get(self, project_id: str, fingerprint: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, project_id, fingerprint)

    @observe(name="security_store_latest")
    async def latest(self, project_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._latest_sync, project_id)

    @observe(name="security_store_upsert")
    async def upsert(self, project_id: str, payload: dict[str, Any], fingerprint: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_sync, project_id, payload, fingerprint)

    def close(self) -> None:
        """No connection is held between calls, so there is nothing to close."""

    # ------------------------------------------------------------------ #

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            # A truncated or corrupted row must not take the endpoint down; the
            # reader gets an empty scan and can rescan.
            logger.warning("security: unreadable payload for project %s", row["project_id"])
            payload = {}
        payload.setdefault("repository", row["repository"])
        payload.setdefault("fingerprint", row["fingerprint"])
        payload.setdefault("created_at", row["created_at"])
        return payload

    def _get_sync(self, project_id: str, fingerprint: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM security_scans WHERE project_id = ? AND fingerprint = ?",
                (project_id, fingerprint),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def _latest_sync(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM security_scans WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def _upsert_sync(self, project_id: str, payload: dict[str, Any], fingerprint: str) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        repository = str(payload.get("repository") or "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO security_scans (project_id, repository, fingerprint, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (project_id, fingerprint) DO UPDATE SET
                    payload = excluded.payload,
                    repository = excluded.repository,
                    created_at = excluded.created_at
                """,
                (project_id, repository, fingerprint, json.dumps(payload), created_at),
            )
        return {**payload, "created_at": created_at}
