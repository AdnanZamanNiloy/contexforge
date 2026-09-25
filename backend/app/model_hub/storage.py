"""SQLite persistence for the Model Hub.

Stores configured models, fallback chains, and the serving configuration.
SQLite matches the existing ``MindMapStore`` / ``RepositoryStore`` pattern
(WAL mode, one short-lived connection per operation) so no connection is ever
shared across threads.

API keys are written to the ``api_key`` column but are stripped by the service
layer before any object leaves the backend — the store itself is the only place
a key is ever read.
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
from observability.tracer import observe

__all__ = ["ModelHubStore"]

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hub_models (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    model_type    TEXT NOT NULL,
    runtime       TEXT NOT NULL,
    provider      TEXT NOT NULL DEFAULT 'custom',
    model_id      TEXT NOT NULL,
    base_url      TEXT,
    api_key       TEXT,
    dimension     INTEGER,
    local_backend TEXT,
    device        TEXT,
    status        TEXT NOT NULL DEFAULT 'untested',
    status_detail TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hub_chains (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    chain_type TEXT NOT NULL,
    model_ids  TEXT NOT NULL DEFAULT '[]',
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hub_serving (
    tier       TEXT PRIMARY KEY,
    mode       TEXT NOT NULL DEFAULT 'disabled',
    target     TEXT,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ModelHubStore:
    """Background-agnostic SQLite store for Model Hub configuration."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or settings.MODEL_HUB_DB_PATH)

    # ------------------------------------------------------------------ #
    # Models
    # ------------------------------------------------------------------ #

    @observe(name="hub_list_models")
    async def list_models(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_models_sync)

    @observe(name="hub_get_model")
    async def get_model(self, model_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_model_sync, model_id)

    @observe(name="hub_create_model")
    async def create_model(self, fields: dict[str, Any]) -> dict[str, Any]:
        model_id = f"model_{uuid.uuid4().hex[:12]}"
        return await asyncio.to_thread(self._create_model_sync, model_id, fields)

    @observe(name="hub_update_model")
    async def update_model(self, model_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._update_model_sync, model_id, fields)

    @observe(name="hub_delete_model")
    async def delete_model(self, model_id: str) -> bool:
        return await asyncio.to_thread(self._delete_model_sync, model_id)

    # ------------------------------------------------------------------ #
    # Chains
    # ------------------------------------------------------------------ #

    @observe(name="hub_list_chains")
    async def list_chains(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_chains_sync)

    @observe(name="hub_get_chain")
    async def get_chain(self, chain_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_chain_sync, chain_id)

    @observe(name="hub_create_chain")
    async def create_chain(self, fields: dict[str, Any]) -> dict[str, Any]:
        chain_id = f"chain_{uuid.uuid4().hex[:12]}"
        return await asyncio.to_thread(self._create_chain_sync, chain_id, fields)

    @observe(name="hub_update_chain")
    async def update_chain(self, chain_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._update_chain_sync, chain_id, fields)

    @observe(name="hub_delete_chain")
    async def delete_chain(self, chain_id: str) -> bool:
        return await asyncio.to_thread(self._delete_chain_sync, chain_id)

    # ------------------------------------------------------------------ #
    # Serving configuration
    # ------------------------------------------------------------------ #

    @observe(name="hub_get_serving")
    async def get_serving(self) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._get_serving_sync)

    @observe(name="hub_set_serving")
    async def set_serving(self, tier: str, mode: str, target: str | None) -> None:
        await asyncio.to_thread(self._set_serving_sync, tier, mode, target)

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

    # --- models ---

    @staticmethod
    def _model_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def _list_models_sync(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM hub_models ORDER BY created_at ASC"
            ).fetchall()
            return [self._model_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def _get_model_sync(self, model_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM hub_models WHERE id = ?", (model_id,)
            ).fetchone()
            return self._model_row_to_dict(row) if row else None
        finally:
            conn.close()

    def _create_model_sync(self, model_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO hub_models (
                        id, name, model_type, runtime, provider, model_id,
                        base_url, api_key, dimension, local_backend, device,
                        status, status_detail, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        model_id,
                        fields["name"],
                        fields["model_type"],
                        fields["runtime"],
                        fields.get("provider", "custom"),
                        fields["model_id"],
                        fields.get("base_url"),
                        fields.get("api_key"),
                        fields.get("dimension"),
                        fields.get("local_backend"),
                        fields.get("device"),
                        fields.get("status", "untested"),
                        fields.get("status_detail"),
                        now,
                        now,
                    ),
                )
            return {"id": model_id, **fields, "created_at": now, "updated_at": now}
        finally:
            conn.close()

    def _update_model_sync(self, model_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        if not fields:
            return self._get_model_sync(model_id)
        fields = {**fields, "updated_at": _now()}
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = [*fields.values(), model_id]
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    f"UPDATE hub_models SET {columns} WHERE id = ?",
                    values,
                )
                if cur.rowcount == 0:
                    return None
            return self._get_model_sync(model_id)
        finally:
            conn.close()

    def _delete_model_sync(self, model_id: str) -> bool:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM hub_models WHERE id = ?", (model_id,))
                if cur.rowcount == 0:
                    return False
                # Remove the model from every chain that referenced it, and
                # disable serving targets that pointed at the deleted model.
                rows = conn.execute("SELECT id, model_ids FROM hub_chains").fetchall()
                for row in rows:
                    members = json.loads(row["model_ids"] or "[]")
                    if model_id in members:
                        pruned = [m for m in members if m != model_id]
                        conn.execute(
                            "UPDATE hub_chains SET model_ids = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(pruned), _now(), row["id"]),
                        )
                conn.execute(
                    "UPDATE hub_serving SET mode = 'disabled', target = NULL, updated_at = ? "
                    "WHERE target = ?",
                    (_now(), model_id),
                )
                self._clear_chain_serving_refs(conn, model_id)
            return True
        finally:
            conn.close()

    @staticmethod
    def _clear_chain_serving_refs(conn: sqlite3.Connection, model_id: str) -> None:
        rows = conn.execute("SELECT id FROM hub_chains").fetchall()
        chain_ids = {r["id"] for r in rows}
        serving = conn.execute("SELECT tier, target FROM hub_serving").fetchall()
        for row in serving:
            if row["target"] and row["target"] not in chain_ids and row["target"] == model_id:
                conn.execute(
                    "UPDATE hub_serving SET mode = 'disabled', target = NULL, updated_at = ? "
                    "WHERE tier = ?",
                    (_now(), row["tier"]),
                )

    # --- chains ---

    @staticmethod
    def _chain_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["model_ids"] = json.loads(data.get("model_ids") or "[]")
        data["enabled"] = bool(data.get("enabled"))
        return data

    def _list_chains_sync(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM hub_chains ORDER BY created_at ASC"
            ).fetchall()
            return [self._chain_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def _get_chain_sync(self, chain_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM hub_chains WHERE id = ?", (chain_id,)
            ).fetchone()
            return self._chain_row_to_dict(row) if row else None
        finally:
            conn.close()

    def _create_chain_sync(self, chain_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        model_ids = json.dumps(fields.get("model_ids", []))
        enabled = 1 if fields.get("enabled", True) else 0
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO hub_chains (id, name, chain_type, model_ids, enabled,
                                            created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chain_id,
                        fields["name"],
                        fields["chain_type"],
                        model_ids,
                        enabled,
                        now,
                        now,
                    ),
                )
            return {
                "id": chain_id,
                "name": fields["name"],
                "chain_type": fields["chain_type"],
                "model_ids": fields.get("model_ids", []),
                "enabled": bool(fields.get("enabled", True)),
                "created_at": now,
                "updated_at": now,
            }
        finally:
            conn.close()

    def _update_chain_sync(self, chain_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        if not fields:
            return self._get_chain_sync(chain_id)
        params: dict[str, Any] = dict(fields)
        if "model_ids" in params:
            params["model_ids"] = json.dumps(params["model_ids"])
        if "enabled" in params:
            params["enabled"] = 1 if params["enabled"] else 0
        params["updated_at"] = _now()
        columns = ", ".join(f"{key} = ?" for key in params)
        values = [*params.values(), chain_id]
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    f"UPDATE hub_chains SET {columns} WHERE id = ?",
                    values,
                )
                if cur.rowcount == 0:
                    return None
            return self._get_chain_sync(chain_id)
        finally:
            conn.close()

    def _delete_chain_sync(self, chain_id: str) -> bool:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute("DELETE FROM hub_chains WHERE id = ?", (chain_id,))
                if cur.rowcount == 0:
                    return False
                conn.execute(
                    "UPDATE hub_serving SET mode = 'disabled', target = NULL, updated_at = ? "
                    "WHERE target = ?",
                    (_now(), chain_id),
                )
            return True
        finally:
            conn.close()

    # --- serving ---

    def _get_serving_sync(self) -> dict[str, dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM hub_serving").fetchall()
            result = {r["tier"]: {"mode": r["mode"], "target": r["target"]} for r in rows}
            for tier in ("llm", "embedding"):
                result.setdefault(tier, {"mode": "disabled", "target": None})
            return result
        finally:
            conn.close()

    def _set_serving_sync(self, tier: str, mode: str, target: str | None) -> None:
        now = _now()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO hub_serving (tier, mode, target, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(tier) DO UPDATE SET
                        mode = excluded.mode,
                        target = excluded.target,
                        updated_at = excluded.updated_at
                    """,
                    (tier, mode, target, now),
                )
        finally:
            conn.close()
