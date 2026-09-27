"""Projects library — store + service unit tests (SQLite temp DB)."""

import sqlite3

import pytest

from app.projects.service import ProjectsService
from app.projects.store import ProjectsStore


@pytest.mark.asyncio
async def test_create_and_list_project(tmp_path):
    store = ProjectsStore(db_path=tmp_path / "projects.db")
    service = ProjectsService(store)

    created = await service.create("AI Research", "Agents and evals", "Research")
    assert created["id"].startswith("proj_")
    assert created["source_count"] == 0

    await service.attach(created["id"], "src-1")
    enriched = await service.list_enriched([{"source_id": "src-1", "type": "pdf"}])
    assert len(enriched) == 1
    assert enriched[0]["source_count"] == 1
    assert enriched[0]["source_types"] == {"pdf": 1}


@pytest.mark.asyncio
async def test_stale_sources_do_not_inflate_counts(tmp_path):
    store = ProjectsStore(db_path=tmp_path / "projects.db")
    service = ProjectsService(store)

    created = await service.create("Crypto", "", "")
    await service.attach(created["id"], "src-gone")
    enriched = await service.list_enriched([{"source_id": "src-live", "type": "web"}])
    assert enriched[0]["source_count"] == 0
    assert enriched[0]["source_ids"] == []


@pytest.mark.asyncio
async def test_migrates_legacy_sources_into_default_project(tmp_path):
    store = ProjectsStore(db_path=tmp_path / "projects.db")
    service = ProjectsService(store)

    enriched = await service.list_enriched(
        [
            {"source_id": "s1", "type": "pdf"},
            {"source_id": "s2", "type": "web"},
        ]
    )
    assert len(enriched) == 1
    assert enriched[0]["name"] == "My Workspace"
    assert enriched[0]["source_count"] == 2


@pytest.mark.asyncio
async def test_update_rejects_blank_name(tmp_path):
    store = ProjectsStore(db_path=tmp_path / "projects.db")
    service = ProjectsService(store)
    created = await service.create("Original", "", "")
    with pytest.raises(ValueError):
        await service.update(created["id"], {"name": "   "})


@pytest.mark.asyncio
async def test_migrates_database_created_before_cover_column(tmp_path):
    """A database shipped without the ``cover`` column must keep working."""
    db_path = tmp_path / "projects.db"
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute(
                "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
                " description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',"
                " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
                " last_opened_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE project_sources (project_id TEXT NOT NULL,"
                " source_id TEXT NOT NULL, added_at TEXT NOT NULL,"
                " PRIMARY KEY (project_id, source_id))"
            )
    finally:
        conn.close()

    store = ProjectsStore(db_path=db_path)
    service = ProjectsService(store)
    created = await service.create("Legacy", "", "")
    assert created["cover"]
    listed = await service.list_enriched([])
    assert len(listed) == 1
    assert listed[0]["cover"]


@pytest.mark.asyncio
async def test_source_category_defaults_and_updates(tmp_path):
    store = ProjectsStore(db_path=tmp_path / "projects.db")
    service = ProjectsService(store)

    created = await service.create("Docs", "", "")
    assert created["source_category"] == "documents"

    tubed = await service.create("Vids", "", "", "youtube")
    assert tubed["source_category"] == "youtube"

    updated = await service.update(tubed["id"], {"source_category": "github"})
    assert updated["source_category"] == "github"


@pytest.mark.asyncio
async def test_legacy_database_gets_unscoped_source_category(tmp_path):
    """Projects predating scoping keep every ingest option ("all")."""
    from datetime import UTC, datetime

    db_path = tmp_path / "projects.db"
    conn = sqlite3.connect(str(db_path))
    now = datetime.now(UTC).isoformat()
    try:
        with conn:
            conn.execute(
                "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
                " description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',"
                " cover TEXT NOT NULL DEFAULT 'aurora',"
                " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
                " last_opened_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE project_sources (project_id TEXT NOT NULL,"
                " source_id TEXT NOT NULL, added_at TEXT NOT NULL,"
                " PRIMARY KEY (project_id, source_id))"
            )
            conn.execute(
                "INSERT INTO projects (id, name, description, category, cover,"
                " created_at, updated_at, last_opened_at)"
                " VALUES ('proj_legacy', 'Legacy', '', '', 'aurora', ?, ?, ?)",
                (now, now, now),
            )
    finally:
        conn.close()

    store = ProjectsStore(db_path=db_path)
    service = ProjectsService(store)
    listed = await service.list_enriched([])
    assert len(listed) == 1
    assert listed[0]["source_category"] == "all"

    fresh = await service.create("Fresh", "", "")
    assert fresh["source_category"] == "documents"


def test_create_schema_rejects_unknown_source_category():
    from pydantic import ValidationError

    from app.projects.schemas import ProjectCreate

    assert ProjectCreate(name="x", source_category="youtube").source_category == "youtube"
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", source_category="podcasts")
