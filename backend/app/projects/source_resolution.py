"""Resolve which source a Studio analysis tool should target.

Every analysis tool (Architecture, Security, Tech Stack, Health) works on a
single source, unlike Repo Chat which spans the whole project selection.  The
resolution order is:

1. an explicit ``source_id`` from the request, validated against the project's
   membership — this is what the UI sends when the user picks a source;
2. the project's persisted ``tool_source_id`` — the last source the user chose,
   so reopening a tool restores their selection;
3. the first GitHub source in the project — a sensible default for projects that
   predate source selection.

Raising ``SourceResolutionError`` with a readable message lets each route map the
failure to its own HTTP status without repeating the logic four times.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.projects.service import ProjectsService

__all__ = ["ResolvedSource", "SourceResolutionError", "resolve_tool_source"]

logger = logging.getLogger(__name__)


class SourceResolutionError(Exception):
    """No usable source could be resolved for a Studio tool."""


@dataclass(frozen=True)
class ResolvedSource:
    source_id: str
    #: ``owner/repo`` for GitHub sources, otherwise the display title.
    label: str


def _is_github(entry: dict, source_id: str) -> bool:
    meta = dict(entry.get("metadata") or {})
    source_type = meta.get("source_type") or entry.get("type")
    return source_type == "github" or str(source_id).startswith("repo:")


def _label_for(entry: dict, source_id: str) -> str:
    meta = dict(entry.get("metadata") or {})
    return str(meta.get("repo") or entry.get("title") or source_id)


async def resolve_tool_source(
    project_id: str,
    explicit_source_id: str | None,
    projects: ProjectsService,
    inventory: list[dict],
) -> ResolvedSource:
    """Resolve the source a tool should analyse, per the documented precedence."""
    project = await projects.get_enriched(project_id, inventory or [])
    if not project:
        raise SourceResolutionError(f"Project '{project_id}' not found.")

    by_id = {entry.get("source_id"): entry for entry in (inventory or []) if entry.get("source_id")}
    member_ids = [str(s) for s in (project.get("source_ids") or [])]

    def resolve_one(source_id: str) -> ResolvedSource | None:
        if not source_id:
            return None
        # Membership is authoritative when the inventory is unavailable; when it
        # is available, an unknown-to-inventory id still resolves so a source
        # mid-ingest is not spuriously rejected.
        if source_id not in member_ids:
            return None
        entry = by_id.get(source_id) or {}
        return ResolvedSource(source_id=source_id, label=_label_for(entry, source_id))

    explicit = (explicit_source_id or "").strip()
    if explicit:
        resolved = resolve_one(explicit)
        if resolved is None:
            raise SourceResolutionError("The selected source is not part of this project.")
        return resolved

    persisted = (project.get("tool_source_id") or "").strip()
    if persisted:
        resolved = resolve_one(persisted)
        if resolved is not None:
            return resolved

    for source_id in member_ids:
        entry = by_id.get(source_id)
        if entry is not None and _is_github(entry, source_id):
            return ResolvedSource(source_id=source_id, label=_label_for(entry, source_id))

    # No GitHub source: fall back to the first member of any type so document
    # and text projects can still be analysed.
    for source_id in member_ids:
        entry = by_id.get(source_id) or {}
        return ResolvedSource(source_id=source_id, label=_label_for(entry, source_id))

    raise SourceResolutionError("This project has no source to analyse.")
