"""SQLite persistence for Repository Intelligence.

Stores one row per analysis run plus its nodes and edges.  SQLite matches the
existing ``BM25Index`` pattern (WAL mode) and keeps structured analysis
metadata queryable.  Incremental re-analysis is supported by keying runs on
the ``commit_sha``.

Each operation opens its own connection (``check_same_thread=False``) and
relies on WAL to coordinate concurrent reads/writes, so background analysis
tasks never share one connection across threads.
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

__all__ = ["RepositoryStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id          TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    name        TEXT NOT NULL,
    full_name   TEXT NOT NULL,
    repo_url    TEXT NOT NULL,
    branch      TEXT NOT NULL,
    commit_sha  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    incremental INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    finished_at TEXT,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS analysis_nodes (
    analysis_id TEXT NOT NULL,
    node_id     TEXT NOT NULL,
    label       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    path        TEXT NOT NULL DEFAULT '',
    files       INTEGER NOT NULL DEFAULT 0,
    loc         INTEGER NOT NULL DEFAULT 0,
    deps        INTEGER NOT NULL DEFAULT 0,
    dependents  INTEGER NOT NULL DEFAULT 0,
    risk        TEXT NOT NULL DEFAULT 'Low',
    risk_score  REAL NOT NULL DEFAULT 0,
    coverage    REAL NOT NULL DEFAULT 0,
    x           REAL,
    y           REAL,
    meta        TEXT NOT NULL DEFAULT '{}',
    signals     TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS analysis_edges (
    analysis_id         TEXT NOT NULL,
    source              TEXT NOT NULL,
    target              TEXT NOT NULL,
    kind                TEXT NOT NULL,
    relationship_source TEXT NOT NULL DEFAULT 'ast',
    confidence          REAL NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_nodes_run ON analysis_nodes(analysis_id);
CREATE INDEX IF NOT EXISTS idx_edges_run ON analysis_edges(analysis_id);
CREATE INDEX IF NOT EXISTS idx_runs_repo ON analysis_runs(owner, name);
"""


class RepositoryStore:
    """Background-agnostic SQLite store for analysis runs."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.REPO_ANALYSIS_DIR / "repo_intelligence.db")

    # ------------------------------------------------------------------ #
    # Run lifecycle
    # ------------------------------------------------------------------ #

    @observe(name="repo_store_create_run")
    async def create_run(self, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._create_run_sync, payload)

    @observe(name="repo_store_update_run")
    async def update_run(self, analysis_id: str, **fields: Any) -> None:
        await asyncio.to_thread(self._update_run_sync, analysis_id, fields)

    @observe(name="repo_store_save_analysis")
    async def save_analysis(
        self,
        analysis_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        summary_json: str,
    ) -> None:
        await asyncio.to_thread(self._save_analysis_sync, analysis_id, nodes, edges, summary_json)

    # ------------------------------------------------------------------ #
    # Read access
    # ------------------------------------------------------------------ #

    async def get_run(self, analysis_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_run_sync, analysis_id)

    async def get_latest_run(self, owner: str, name: str, exclude_run_id: str | None = None) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_latest_run_sync, owner, name, exclude_run_id)

    async def get_run_overview(self, analysis_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_run_overview_sync, analysis_id)

    async def list_runs(self, owner: str, name: str, limit: int = 20) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_runs_sync, owner, name, limit)

    async def get_nodes(self, analysis_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_nodes_sync, analysis_id)

    async def get_edges(self, analysis_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_edges_sync, analysis_id)

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

    def _create_run_sync(self, payload: dict[str, Any]) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO analysis_runs
                    (id, owner, name, full_name, repo_url, branch, commit_sha,
                     status, progress, error, incremental, created_at, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["id"],
                        payload["owner"],
                        payload["name"],
                        payload["full_name"],
                        payload["repo_url"],
                        payload["branch"],
                        payload.get("commit", ""),
                        payload.get("status", "queued"),
                        payload.get("progress", 0),
                        payload.get("error"),
                        int(payload.get("incremental", False)),
                        _dt(payload.get("created_at")),
                        payload.get("finished_at"),
                    ),
                )
        finally:
            conn.close()

    def _update_run_sync(self, analysis_id: str, fields: dict[str, Any]) -> None:
        allowed = {"status", "progress", "error", "commit_sha", "finished_at", "incremental", "summary_json"}
        sets = [k for k in fields if k in allowed]
        if not sets:
            return
        conn = self._connect()
        try:
            values = [fields[k] for k in sets]
            # Progress must never regress (the final 100 could race a trailing
            # progress update from the analysis callback).
            if "progress" in sets:
                current = conn.execute(
                    "SELECT progress, status FROM analysis_runs WHERE id = ?",
                    (analysis_id,),
                ).fetchone()
                if current is not None:
                    new_progress = fields["progress"]
                    if current["status"] == "complete":
                        values[sets.index("progress")] = 100
                    else:
                        values[sets.index("progress")] = max(current["progress"], new_progress)
            values.append(analysis_id)
            with conn:
                conn.execute(f"UPDATE analysis_runs SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", values)
        finally:
            conn.close()

    def _save_analysis_sync(
        self,
        analysis_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        summary_json: str,
    ) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute("DELETE FROM analysis_nodes WHERE analysis_id = ?", (analysis_id,))
                conn.execute("DELETE FROM analysis_edges WHERE analysis_id = ?", (analysis_id,))
                conn.executemany(
                    """
                    INSERT INTO analysis_nodes
                    (analysis_id, node_id, label, kind, path, files, loc, deps,
                     dependents, risk, risk_score, coverage, x, y, meta, signals)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            analysis_id,
                            n["id"],
                            n.get("label", ""),
                            n.get("kind", "file"),
                            n.get("path", ""),
                            n.get("files", 0),
                            n.get("loc", 0),
                            n.get("deps", 0),
                            n.get("dependents", 0),
                            n.get("risk", "Low"),
                            n.get("risk_score", 0.0),
                            n.get("coverage", 0.0),
                            n.get("x"),
                            n.get("y"),
                            json.dumps(n.get("meta", {}), separators=(",", ":")),
                            json.dumps(n.get("signals", {}), separators=(",", ":")),
                        )
                        for n in nodes
                    ],
                )
                conn.executemany(
                    """
                    INSERT INTO analysis_edges
                    (analysis_id, source, target, kind, relationship_source, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            analysis_id,
                            e["source"],
                            e["target"],
                            e.get("kind", "imports"),
                            e.get("relationship_source", "ast"),
                            e.get("confidence", 1.0),
                        )
                        for e in edges
                    ],
                )
                conn.execute(
                    """
                    UPDATE analysis_runs SET status = 'complete', progress = 100,
                    summary_json = ?, finished_at = ?, commit_sha = ?
                    WHERE id = ?
                    """,
                    (summary_json, _dt(datetime.now(UTC)), _last_commit(nodes), analysis_id),
                )
        finally:
            conn.close()

    def _get_run_sync(self, analysis_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (analysis_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _get_latest_run_sync(self, owner: str, name: str, exclude_run_id: str | None = None) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            query = """SELECT * FROM analysis_runs
                       WHERE owner = ? AND name = ?
                         AND status = 'complete' AND commit_sha != ''"""
            params: list[Any] = [owner, name]
            if exclude_run_id:
                query += " AND id != ?"
                params.append(exclude_run_id)
            query += " ORDER BY created_at DESC LIMIT 1"
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _get_run_overview_sync(self, analysis_id: str) -> dict[str, Any] | None:
        run = self._get_run_sync(analysis_id)
        if run is None:
            return None
        conn = self._connect()
        try:
            node_count = conn.execute(
                "SELECT COUNT(*) AS c FROM analysis_nodes WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()["c"]
            edge_count = conn.execute(
                "SELECT COUNT(*) AS c FROM analysis_edges WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()["c"]
            run["node_count"] = node_count
            run["edge_count"] = edge_count
            return run
        finally:
            conn.close()

    def _list_runs_sync(self, owner: str, name: str, limit: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT id, owner, name, full_name, branch, commit_sha, status,
                          progress, created_at, finished_at, error
                   FROM analysis_runs WHERE owner = ? AND name = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (owner, name, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _get_nodes_sync(self, analysis_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT node_id, label, kind, path, files, loc, deps, dependents,
                          risk, risk_score, coverage, x, y, meta, signals
                   FROM analysis_nodes WHERE analysis_id = ? ORDER BY node_id""",
                (analysis_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["id"] = d.pop("node_id")
                d["meta"] = json.loads(d.get("meta") or "{}")
                d["signals"] = json.loads(d.get("signals") or "{}")
                out.append(d)
            return out
        finally:
            conn.close()

    def _get_edges_sync(self, analysis_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT source, target, kind, relationship_source, confidence
                   FROM analysis_edges WHERE analysis_id = ?""",
                (analysis_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def _dt(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _last_commit(nodes: list[dict[str, Any]]) -> str:
    for n in nodes:
        if n.get("kind") == "repo":
            return n.get("meta", {}).get("commit", "")
    return ""
