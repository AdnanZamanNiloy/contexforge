"""SQLite persistence for generated architecture diagrams.

One row per ``(project_id, source_id, fingerprint)``.  The fingerprint is a
digest of the source's indexed file paths, so it stands in for a commit SHA:
re-ingesting an unchanged source produces the same paths and therefore the same
key, while any change to the file set produces a new one and invalidates the
diagram automatically.  That avoids a second GitHub round-trip purely to read a
SHA.

The ``source_id`` is part of the key so every source in a project keeps its own
diagram: selecting a different source shows that source's stored map, and
generating one source's map never overwrites another's.

Same WAL-on-its-own-connection pattern as :mod:`app.mindmap.storage`.
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

__all__ = ["ArchitectureStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS architecture (
    project_id    TEXT NOT NULL,
    source_id     TEXT NOT NULL DEFAULT '',
    fingerprint   TEXT NOT NULL,
    repository    TEXT NOT NULL,
    branch        TEXT NOT NULL DEFAULT 'main',
    mermaid       TEXT NOT NULL,
    explanation   TEXT NOT NULL DEFAULT '',
    node_count    INTEGER NOT NULL DEFAULT 0,
    edge_count    INTEGER NOT NULL DEFAULT 0,
    group_count   INTEGER NOT NULL DEFAULT 0,
    truncated_paths INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (project_id, source_id, fingerprint)
);
"""


class ArchitectureStore:
    """Background-agnostic SQLite store for generated diagrams."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.ARCHITECTURE_DB_PATH)

    @observe(name="architecture_store_get")
    async def get(self, project_id: str, source_id: str, fingerprint: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, project_id, source_id, fingerprint)

    @observe(name="architecture_store_upsert")
    async def upsert(self, project_id: str, source_id: str, record: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._upsert_sync, project_id, source_id, record)

    @observe(name="architecture_store_latest")
    async def latest(self, project_id: str, source_id: str) -> dict[str, Any] | None:
        """Return the most recent diagram for a project + source.

        Reads are scoped to the source so switching sources shows that source's
        own diagram rather than whichever was generated last.
        """
        return await asyncio.to_thread(self._latest_sync, project_id, source_id)

    async def clear(self, project_id: str) -> None:
        await asyncio.to_thread(self._clear_sync, project_id)

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
        self._migrate_sync(conn)
        return conn

    @staticmethod
    def _migrate_sync(conn: sqlite3.Connection) -> None:
        info = conn.execute("PRAGMA table_info(architecture)").fetchall()
        existing = {row[1] for row in info}
        if "source_id" in existing:
            return
        # The legacy primary key was (project_id, fingerprint); SQLite cannot
        # widen a primary key with ALTER TABLE, so pre-existing databases are
        # rebuilt onto the new (project_id, source_id, fingerprint) key.  Old
        # rows are preserved under a blank source_id.
        if not existing:
            return
        logger.info("architecture: rebuilding table onto per-source key")
        with conn:
            conn.execute("ALTER TABLE architecture RENAME TO architecture_legacy")
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO architecture ("
                " project_id, source_id, fingerprint, repository, branch, mermaid,"
                " explanation, node_count, edge_count, group_count, truncated_paths, created_at"
                " ) SELECT project_id, '', fingerprint, repository, branch, mermaid,"
                " explanation, node_count, edge_count, group_count, truncated_paths, created_at"
                " FROM architecture_legacy"
            )
            conn.execute("DROP TABLE architecture_legacy")
        conn.commit()

    _COLUMNS = (
        "project_id, source_id, fingerprint, repository, branch, mermaid, explanation, "
        "node_count, edge_count, group_count, truncated_paths, created_at"
    )

    def _get_sync(self, project_id: str, source_id: str, fingerprint: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT {self._COLUMNS} FROM architecture WHERE project_id = ? AND source_id = ? AND fingerprint = ?",
                (project_id, source_id, fingerprint),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _latest_sync(self, project_id: str, source_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                f"SELECT {self._COLUMNS} FROM architecture"
                " WHERE project_id = ? AND source_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id, source_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _upsert_sync(self, project_id: str, source_id: str, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        source_id = source_id or ""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO architecture (
                        project_id, source_id, fingerprint, repository, branch, mermaid,
                        explanation, node_count, edge_count, group_count,
                        truncated_paths, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, source_id, fingerprint) DO UPDATE SET
                        repository = excluded.repository,
                        branch = excluded.branch,
                        mermaid = excluded.mermaid,
                        explanation = excluded.explanation,
                        node_count = excluded.node_count,
                        edge_count = excluded.edge_count,
                        group_count = excluded.group_count,
                        truncated_paths = excluded.truncated_paths,
                        created_at = excluded.created_at
                    """,
                    (
                        project_id,
                        source_id,
                        record["fingerprint"],
                        record["repository"],
                        record.get("branch") or "main",
                        record["mermaid"],
                        record.get("explanation") or "",
                        int(record.get("node_count") or 0),
                        int(record.get("edge_count") or 0),
                        int(record.get("group_count") or 0),
                        int(record.get("truncated_paths") or 0),
                        now,
                    ),
                )
            stored = dict(
                conn.execute(
                    f"SELECT {self._COLUMNS} FROM architecture"
                    " WHERE project_id = ? AND source_id = ? AND fingerprint = ?",
                    (project_id, source_id, record["fingerprint"]),
                ).fetchone()
            )
            return stored
        finally:
            conn.close()

    def _clear_sync(self, project_id: str) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute("DELETE FROM architecture WHERE project_id = ?", (project_id,))
        finally:
            conn.close()
