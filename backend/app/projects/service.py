"""Projects service — CRUD + live enrichment from the source inventory.

The store owns metadata and membership.  This service reconciles that with
the live FAISS/BM25 inventory on every read so:

- ``source_count`` reflects sources that still exist (deleted sources are
  pruned lazily from the membership map),
- the library shows a per-type breakdown for each project card,
- a fresh install with pre-existing sources migrates them into a default
  project instead of showing an empty library.
"""

from __future__ import annotations

import logging
from typing import Any

from .store import ProjectsStore

__all__ = ["ProjectsService"]

logger = logging.getLogger(__name__)


class ProjectsService:
    def __init__(self, store: ProjectsStore) -> None:
        self._store = store

    # -- writes ---------------------------------------------------------

    async def create(self, name: str, description: str = "", category: str = "") -> dict[str, Any]:
        project = await self._store.create_project(name, description, category)
        return self._present(project, {})

    async def update(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        clean = {k: v for k, v in fields.items() if k in {"name", "description", "category"} and v is not None}
        if not clean:
            project = await self._store.get_project(project_id)
            return self._present(project, {}) if project else None
        try:
            project = await self._store.update_project(project_id, clean)
        except ValueError:
            raise
        return self._present(project, {}) if project else None

    async def delete(self, project_id: str) -> bool:
        return await self._store.delete_project(project_id)

    async def touch(self, project_id: str) -> dict[str, Any] | None:
        project = await self._store.touch_opened(project_id)
        return self._present(project, {}) if project else None

    async def attach(self, project_id: str, source_id: str) -> bool:
        return await self._store.attach_source(project_id, source_id)

    async def detach(self, project_id: str, source_id: str) -> bool:
        return await self._store.detach_source(project_id, source_id)

    # -- reads (enriched) ------------------------------------------------

    async def list_enriched(self, inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """List projects with live counts; migrate legacy sources if needed."""
        projects = await self._store.list_projects()
        by_id = {s.get("source_id"): s for s in inventory if s.get("source_id")}

        if not projects and by_id:
            # First run after upgrade: adopt every existing source so nothing
            # the user already ingested disappears from the library.
            migrated = await self._store.create_project(
                "My Workspace", "Migrated from your existing knowledge base.", "General"
            )
            for sid in by_id:
                await self._store.attach_source(migrated["id"], sid)
            projects = await self._store.list_projects()
            logger.info("projects: migrated %d existing sources into default project", len(by_id))

        enriched = [self._present(p, by_id) for p in projects]
        # Prune membership rows that point at deleted sources (lazy, best-effort).
        for raw in projects:
            stale = [sid for sid in raw.get("source_ids", []) if sid not in by_id] if by_id else []
            for sid in stale:
                try:
                    await self._store.detach_source(raw["id"], sid)
                except Exception:
                    pass
        return enriched

    async def get_enriched(self, project_id: str, inventory: list[dict[str, Any]]) -> dict[str, Any] | None:
        project = await self._store.get_project(project_id)
        if not project:
            return None
        by_id = {s.get("source_id"): s for s in inventory if s.get("source_id")}
        return self._present(project, by_id)

    # -- presentation ----------------------------------------------------

    @staticmethod
    def _present(raw: dict[str, Any] | None, by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        if not raw:
            return None
        live_ids = (
            [sid for sid in raw.get("source_ids", []) if sid in by_id] if by_id else list(raw.get("source_ids", []))
        )
        # When the inventory is unavailable (e.g. storage error) fall back to
        # stored membership so the library never blanks out.
        types: dict[str, int] = {}
        for sid in live_ids:
            t = (by_id.get(sid) or {}).get("type", "unknown") if by_id else "unknown"
            types[t] = types.get(t, 0) + 1
        return {
            "id": raw["id"],
            "name": raw["name"],
            "description": raw.get("description", ""),
            "category": raw.get("category", ""),
            "cover": raw.get("cover", "aurora"),
            "source_ids": live_ids if by_id else list(raw.get("source_ids", [])),
            "source_count": len(live_ids) if by_id else raw.get("source_count", 0),
            "source_types": types,
            "last_source_at": None,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "last_opened_at": raw.get("last_opened_at"),
        }
