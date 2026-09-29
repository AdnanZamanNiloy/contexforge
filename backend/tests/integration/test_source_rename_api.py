"""HTTP tests for the source rename endpoint.

``PATCH /ingest/source/{id}`` records a display-title override, and
``GET /ingest/sources`` layers it over the title derived from chunk metadata.
Both are exercised here with a temporary override store and a fake ingest
service, so no vector store or provider call is involved.
"""

from __future__ import annotations

import httpx
import pytest

from app.dependencies import get_ingest_service, get_source_meta_store
from app.main import app
from app.sources.storage import SourceMetaStore


class _FakeOrchestrator:
    def __init__(self) -> None:
        # The route reaches for the private _faiss / _bm25 handles.
        self._faiss = self
        self._bm25 = self
        self._groups = [
            {"source_id": "repo:owner/name", "title": "owner/name", "type": "github", "chunks": 4},
            {"source_id": "doc:handbook", "title": "handbook.pdf", "type": "pdf", "chunks": 9},
        ]

    async def get_source_info(self):
        return [dict(g) for g in self._groups]

    async def count(self):
        return 13

    async def delete_source(self, source_id):
        return 4

    async def clear_all(self):
        return {"faiss_chunks_removed": 13, "bm25_chunks_removed": 0}


class _FakeIngestService:
    def __init__(self) -> None:
        self._orchestrator = _FakeOrchestrator()

    async def delete_source(self, source_id):
        return await self._orchestrator.delete_source(source_id)

    async def clear_all(self):
        return await self._orchestrator.clear_all()


@pytest.fixture
def meta_store(tmp_path):
    return SourceMetaStore(db_path=tmp_path / "sources.db")


@pytest.fixture
def client(meta_store):
    ingest = _FakeIngestService()
    app.dependency_overrides[get_ingest_service] = lambda: ingest
    app.dependency_overrides[get_source_meta_store] = lambda: meta_store
    # The projects store would otherwise write to the real database.
    from app.dependencies import get_projects_store

    class _NullProjects:
        async def remove_source_everywhere(self, source_id):
            return None

        async def clear_membership(self):
            return None

    app.dependency_overrides[get_projects_store] = lambda: _NullProjects()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rename_persists_and_replaces_the_derived_title(client):
    async with client as c:
        response = await c.patch(
            "/ingest/source/repo:owner/name",
            json={"title": "Contexforge"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Contexforge"

        listed = await c.get("/ingest/sources")
        titles = {s["source_id"]: s["title"] for s in listed.json()["sources"]}
        assert titles["repo:owner/name"] == "Contexforge"
        # Untouched sources keep their derived titles.
        assert titles["doc:handbook"] == "handbook.pdf"


@pytest.mark.asyncio
async def test_rename_trims_whitespace(client):
    async with client as c:
        response = await c.patch("/ingest/source/doc:handbook", json={"title": "  Runbook  "})
        assert response.json()["title"] == "Runbook"


@pytest.mark.asyncio
async def test_blank_title_is_rejected(client):
    async with client as c:
        response = await c.patch("/ingest/source/doc:handbook", json={"title": "   "})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_title_is_rejected(client):
    async with client as c:
        response = await c.patch("/ingest/source/doc:handbook", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_deleting_a_source_drops_its_rename(client, meta_store):
    async with client as c:
        await c.patch("/ingest/source/repo:owner/name", json={"title": "Contexforge"})
        deleted = await c.delete("/ingest/source/repo:owner/name")
        assert deleted.status_code == 200
        # The rename must not outlive the source.
        assert await meta_store.all_titles() == {}


