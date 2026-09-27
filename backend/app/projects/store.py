"""SQLite persistence for the Projects library.

A project is a named collection of sources around one topic.  Sources
themselves live in FAISS/BM25 — this store only keeps project metadata plus
the ``project_id → source_id`` membership map, so the library survives
restarts without touching the retrieval pipeline.

Follows the existing ``MindMapStore`` / ``ModelHubStore`` pattern: WAL mode,
one short-lived connection per operation, never shared across threads.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings

__all__ = ["ProjectsStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    cover           TEXT NOT NULL DEFAULT 'aurora',
    source_category TEXT NOT NULL DEFAULT 'documents',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_opened_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_sources (
    project_id TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (project_id, source_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


_COVERS = ("aurora", "ember", "tide", "moss", "violet", "slate")

# Columns added after the first shipped schema, applied idempotently by
# ``_migrate_sync`` to databases created before they existed.
_MIGRATIONS = (
    ("cover", "TEXT NOT NULL DEFAULT 'aurora'"),
    # Pre-existing projects predate source scoping: keep every ingest option.
    ("source_category", "TEXT NOT NULL DEFAULT 'all'"),
)


def _cover_for(project_id: str) -> str:
    digest = sum(ord(c) for c in project_id) if project_id else 0
    return _COVERS[digest % len(_COVERS)]


class ProjectsStore:
    """Background-agnostic SQLite store for project metadata + membership."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.PROJECTS_DB_PATH)

    # -- projects ------------------------------------------------------

    async def list_projects(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_sync)

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, project_id)

    async def create_project(
        self, name: str, description: str = "", category: str = "", source_category: str = "documents"
    ) -> dict[str, Any]:
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        return await asyncio.to_thread(self._create_sync, project_id, name, description, category, source_category)

    async def update_project(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._update_sync, project_id, fields)

    async def delete_project(self, project_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, project_id)

    async def touch_opened(self, project_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._touch_sync, project_id)

    # -- membership ----------------------------------------------------

    async def list_source_ids(self, project_id: str) -> list[str]:
        return await asyncio.to_thread(self._list_sources_sync, project_id)

    async def list_all_membership(self) -> dict[str, list[str]]:
        return await asyncio.to_thread(self._membership_sync)

    async def attach_source(self, project_id: str, source_id: str) -> bool:
        return await asyncio.to_thread(self._attach_sync, project_id, source_id)

    async def detach_source(self, project_id: str, source_id: str) -> bool:
        return await asyncio.to_thread(self._detach_sync, project_id, source_id)

    async def remove_source_everywhere(self, source_id: str) -> int:
        return await asyncio.to_thread(self._remove_everywhere_sync, source_id)

    async def clear_membership(self) -> int:
        return await asyncio.to_thread(self._clear_membership_sync)

    def close(self) -> None:
        """No persistent connection; retained for the common close_all API."""

    # -- sync internals -------------------------------------------------

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
        """Add columns missing from databases created by an older schema.

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so a
        database shipped or created before a column existed would otherwise
        crash every write with ``no such column``.
        """
        existing = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        for name, ddl in _MIGRATIONS:
            if name not in existing:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {name} {ddl}")
                logger.info("projects: migrated database (added column %s)", name)
        conn.commit()

    def _row_to_dict(self, row: sqlite3.Row, source_ids: list[str]) -> dict[str, Any]:
        data = dict(row)
        data["source_ids"] = source_ids
        data["source_count"] = len(source_ids)
        return data

    def _sources_for(self, conn: sqlite3.Connection, project_id: str) -> list[str]:
        rows = conn.execute(
            "SELECT source_id FROM project_sources WHERE project_id = ? ORDER BY added_at ASC",
            (project_id,),
        ).fetchall()
        return [r["source_id"] for r in rows]

    def _list_sync(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM projects ORDER BY last_opened_at DESC").fetchall()
            return [self._row_to_dict(r, self._sources_for(conn, r["id"])) for r in rows]
        finally:
            conn.close()

    def _get_sync(self, project_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not row:
                return None
            return self._row_to_dict(row, self._sources_for(conn, project_id))
        finally:
            conn.close()

    def _create_sync(
        self, project_id: str, name: str, description: str, category: str, source_category: str
    ) -> dict[str, Any]:
        now = _now()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO projects (id, name, description, category, cover, source_category,"
                    " created_at, updated_at, last_opened_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project_id,
                        name,
                        description or "",
                        category or "",
                        _cover_for(project_id),
                        source_category or "documents",
                        now,
                        now,
                        now,
                    ),
                )
            return {
                "id": project_id,
                "name": name,
                "description": description or "",
                "category": category or "",
                "cover": _cover_for(project_id),
                "source_category": source_category or "documents",
                "source_ids": [],
                "source_count": 0,
                "created_at": now,
                "updated_at": now,
                "last_opened_at": now,
            }
        finally:
            conn.close()

    def _update_sync(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {k: v for k, v in fields.items() if k in {"name", "description", "category", "source_category"}}
        if "name" in allowed and not str(allowed["name"]).strip():
            raise ValueError("Project name must not be blank.")
        allowed["updated_at"] = _now()
        columns = ", ".join(f"{k} = ?" for k in allowed)
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    f"UPDATE projects SET {columns} WHERE id = ?",
                    [*allowed.values(), project_id],
                )
                if cur.rowcount == 0:
                    return None
            return self._get_sync(project_id)
        finally:
            conn.close()

    def _delete_sync(self, project_id: str) -> bool:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                conn.execute("DELETE FROM project_sources WHERE project_id = ?", (project_id,))
                return cur.rowcount > 0
        finally:
            conn.close()

    def _touch_sync(self, project_id: str) -> dict[str, Any] | None:
        now = _now()
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE projects SET last_opened_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, project_id),
                )
                if cur.rowcount == 0:
                    return None
            return self._get_sync(project_id)
        finally:
            conn.close()

    def _list_sources_sync(self, project_id: str) -> list[str]:
        conn = self._connect()
        try:
            return self._sources_for(conn, project_id)
        finally:
            conn.close()

    def _membership_sync(self) -> dict[str, list[str]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT project_id, source_id FROM project_sources ORDER BY added_at ASC").fetchall()
            membership: dict[str, list[str]] = {}
            for r in rows:
                membership.setdefault(r["project_id"], []).append(r["source_id"])
            return membership
        finally:
            conn.close()

    def _attach_sync(self, project_id: str, source_id: str) -> bool:
        conn = self._connect()
        try:
            exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not exists:
                return False
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO project_sources (project_id, source_id, added_at) VALUES (?, ?, ?)",
                    (project_id, source_id, _now()),
                )
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (_now(), project_id),
                )
            return True
        finally:
            conn.close()

    def _detach_sync(self, project_id: str, source_id: str) -> bool:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "DELETE FROM project_sources WHERE project_id = ? AND source_id = ?",
                    (project_id, source_id),
                )
                if cur.rowcount:
                    conn.execute(
                        "UPDATE projects SET updated_at = ? WHERE id = ?",
                        (_now(), project_id),
                    )
                return cur.rowcount > 0
        finally:
            conn.close()

    def _remove_everywhere_sync(self, source_id: str) -> int:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM project_sources WHERE source_id = ?", (source_id,))
                return cur.rowcount
        finally:
            conn.close()

    def _clear_membership_sync(self) -> int:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM project_sources")
                return cur.rowcount
        finally:
            conn.close()
