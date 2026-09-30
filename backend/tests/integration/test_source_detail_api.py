"""HTTP tests for the source inspection endpoints.

``GET /ingest/source/{id}`` and ``GET /ingest/source/{id}/content`` expose what
a source actually contributed to the index. They are exercised here against a
fake ingest service, so no vector store or provider call is involved.

The route ordering matters and is easy to regress: ``{source_id:path}`` is greedy,
so if the catch-all detail route were declared first it would swallow a trailing
``/content`` and report the whole string as an unknown source. That case is
pinned below.
"""

from __future__ import annotations

import httpx
import pytest

from app.dependencies import get_ingest_service, get_source_meta_store
from app.main import app
from app.sources.storage import SourceMetaStore

WEB_ID = "65361929-b435-4463-9338-658d78e3d5f3"
REPO_ID = "repo:AdnanZamanNiloy/diabetescare-ai"


class _FakeFaiss:
    def __init__(self) -> None:
        self._chunks = {
            WEB_ID: [
                _chunk(
                    f"{WEB_ID}:{i}",
                    f"Page text {i}",
                    source_type="web",
                    title="A university",
                    chunk_index=i,
                    url="https://example.org/uni",
                )
                for i in range(3)
            ],
            REPO_ID: [
                _chunk(
                    f"{REPO_ID}:LICENSE:0",
                    "MIT text",
                    source_type="github",
                    repo="AdnanZamanNiloy/diabetescare-ai",
                    path="LICENSE",
                    chunk_index=0,
                ),
                _chunk(
                    f"{REPO_ID}:app.py:0",
                    "app text",
                    source_type="github",
                    repo="AdnanZamanNiloy/diabetescare-ai",
                    path="backend/app.py",
                    chunk_index=0,
                ),
            ],
        }

    async def get_chunks_by_source_id(self, source_id):
        return list(self._chunks.get(source_id, []))


def _chunk(chunk_id, text, **metadata):
    from types import MappingProxyType

    return type(
        "FakeChunk",
        (),
        {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": MappingProxyType(dict(metadata)),
            "source_id": metadata.get("source_id", ""),
        },
    )()


class _FakeIngestService:
    def __init__(self) -> None:
        self._orchestrator = type("Orch", (), {"_faiss": _FakeFaiss()})()


@pytest.fixture
def meta_store(tmp_path):
    return SourceMetaStore(db_path=tmp_path / "sources.db")


@pytest.fixture
def client(meta_store):
    app.dependency_overrides[get_ingest_service] = lambda: _FakeIngestService()
    app.dependency_overrides[get_source_meta_store] = lambda: meta_store

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
async def test_detail_reports_extraction_stats(client):
    async with client as c:
        response = await c.get(f"/ingest/source/{WEB_ID}")

        assert response.status_code == 200
        body = response.json()
        assert body["source_type"] == "web"
        assert body["chunk_count"] == 3
        assert body["char_count"] == sum(len(f"Page text {i}") for i in range(3))
        assert body["renamed"] is False


@pytest.mark.asyncio
async def test_detail_reports_the_original_upload_as_unavailable(client):
    async with client as c:
        body = (await c.get(f"/ingest/source/{WEB_ID}")).json()

        # Honest rather than implied: the bytes are not retained.
        assert body["file_available"] is False


@pytest.mark.asyncio
async def test_detail_reflects_a_rename(client, meta_store):
    await meta_store.set_title(WEB_ID, "My uni notes")
    async with client as c:
        body = (await c.get(f"/ingest/source/{WEB_ID}")).json()

        assert body["title"] == "My uni notes"
        assert body["derived_title"] == "A university"
        assert body["renamed"] is True


@pytest.mark.asyncio
async def test_detail_handles_a_source_id_containing_a_slash(client):
    async with client as c:
        response = await c.get(f"/ingest/source/{REPO_ID}")

        assert response.status_code == 200
        body = response.json()
        assert body["source_type"] == "github"
        assert body["file_paths"] == ["LICENSE", "backend/app.py"]


@pytest.mark.asyncio
async def test_detail_titles_a_repository_by_its_repo_not_its_first_file(client):
    # The list resolves a repository to `repo`; the detail view must agree, or
    # it would title a whole repository "MIT License" because that file happened
    # to be indexed first.
    async with client as c:
        body = (await c.get(f"/ingest/source/{REPO_ID}")).json()

        assert body["title"] == "AdnanZamanNiloy/diabetescare-ai"
        assert body["derived_title"] == "AdnanZamanNiloy/diabetescare-ai"


@pytest.mark.asyncio
async def test_detail_404s_for_an_unknown_source(client):
    async with client as c:
        response = await c.get("/ingest/source/no-such-source")

        assert response.status_code == 404
        assert "not in the index" in response.json()["detail"]


@pytest.mark.asyncio
async def test_content_returns_the_indexed_text(client):
    async with client as c:
        response = await c.get(f"/ingest/source/{WEB_ID}/content")

        assert response.status_code == 200
        body = response.json()
        assert body["total_chunks"] == 3
        assert body["truncated"] is False
        assert body["chunks"][0]["text"] == "Page text 0"


@pytest.mark.asyncio
async def test_content_route_is_not_swallowed_by_the_path_catch_all(client):
    # Regression guard: `{source_id:path}` is greedy, so the catch-all detail
    # route must stay declared after this one.
    async with client as c:
        response = await c.get(f"/ingest/source/{WEB_ID}/content")

        assert response.status_code == 200
        assert "chunks" in response.json()
        # And the detail route must still work on its own.
        assert (await c.get(f"/ingest/source/{WEB_ID}")).status_code == 200


@pytest.mark.asyncio
async def test_content_404s_for_an_unknown_source(client):
    async with client as c:
        assert (await c.get("/ingest/source/nope/content")).status_code == 404
