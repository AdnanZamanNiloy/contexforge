"""SQLite cache for security scans.

One row per ``(project_id, source_id, fingerprint)``, holding the finished
payload as JSON.  A GitHub loader never records a commit SHA, so the fingerprint
is the honest equivalent — the same file list means the same scan.  Keying on
``source_id`` as well keeps every source's scan separate within a project.
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

__all__ = ["SecurityStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_scans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT    NOT NULL,
    source_id   TEXT    NOT NULL DEFAULT '',
    repository  TEXT    NOT NULL DEFAULT '',
    fingerprint TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    UNIQUE (project_id, source_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_security_project
    ON security_scans (project_id, created_at DESC);
"""


class SecurityStore:
    """Persists the most recent scan per project + source + fingerprint."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = Path(db_path) if db_path else settings.SECURITY_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_sync(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _migrate_sync(conn: sqlite3.Connection) -> None:
        info = conn.execute("PRAGMA table_info(security_scans)").fetchall()
        existing = {row[1] for row in info}
        if not existing or "source_id" in existing:
            return
        # The legacy UNIQUE constraint was (project_id, fingerprint); SQLite
        # cannot alter a constraint, so the table is rebuilt onto the per-source
        # key.  Pre-existing rows survive under a blank source_id.
        logger.info("security: rebuilding table onto per-source key")
        with conn:
            conn.execute("ALTER TABLE security_scans RENAME TO security_scans_legacy")
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO security_scans ("
                " project_id, source_id, repository, fingerprint, payload, created_at"
                " ) SELECT project_id, '', repository, fingerprint, payload, created_at"
                " FROM security_scans_legacy"
            )
            conn.execute("DROP TABLE security_scans_legacy")

    @observe(name="security_store_get")
    async def get(self, project_id: str, source_id: str, fingerprint: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, project_id, source_id, fingerprint)

    @observe(name="security_store_latest")
    async def latest(self, project_id: str, source_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._latest_sync, project_id, source_id)

    @observe(name="security_store_upsert")
    async def upsert(
        self, project_id: str, source_id: str, payload: dict[str, Any], fingerprint: str
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_sync, project_id, source_id, payload, fingerprint)

    def close(self) -> None:
        """No connection is held between calls, so there is nothing to close."""

    # ------------------------------------------------------------------ #

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload"])
        except TypeError, ValueError:
            # A truncated or corrupted row must not take the endpoint down; the
            # reader gets an empty scan and can rescan.
            logger.warning("security: unreadable payload for project %s", row["project_id"])
            payload = {}
        payload.setdefault("repository", row["repository"])
        payload["source_id"] = row["source_id"] or ""
        payload.setdefault("fingerprint", row["fingerprint"])
        payload.setdefault("created_at", row["created_at"])
        return payload

    def _get_sync(self, project_id: str, source_id: str, fingerprint: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM security_scans WHERE project_id = ? AND source_id = ? AND fingerprint = ?",
                (project_id, source_id or "", fingerprint),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def _latest_sync(self, project_id: str, source_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM security_scans WHERE project_id = ? AND source_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id, source_id or ""),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def _upsert_sync(
        self, project_id: str, source_id: str, payload: dict[str, Any], fingerprint: str
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        repository = str(payload.get("repository") or "")
        source_id = source_id or ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO security_scans
                    (project_id, source_id, repository, fingerprint, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (project_id, source_id, fingerprint) DO UPDATE SET
                    payload = excluded.payload,
                    repository = excluded.repository,
                    created_at = excluded.created_at
                """,
                (project_id, source_id, repository, fingerprint, json.dumps(payload), created_at),
            )
        return {**payload, "created_at": created_at}
