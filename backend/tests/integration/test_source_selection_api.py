"""HTTP contract tests for scoping a request to a selection of sources.

Covers the two endpoints the project workspace drives from its sidebar
selection:

- ``POST /query``   — must accept ``source_ids`` and scope retrieval to them.
- ``POST /mindmap/generate`` and ``GET /mindmap/{key}`` — must accept a
  multi-source selection and address it with a stable composite key.

The services are overridden with fakes so no provider call, API key or real
database is involved; what is under test is the wiring from request body to
service call and back out through the response schema.
"""

from __future__ import annotations

import httpx
import pytest

from app.dependencies import get_mindmap_service, get_query_service
from app.main import app
from core.types import GenerationResult


class _FakeQueryService:
    """Captures the QueryRequest it was handed."""

    def __init__(self) -> None:
        self.request = None

    async def answer(self, request):
        self.request = request
        return GenerationResult(answer="ok", sources=[], latency_ms={"total": 1.0})

    async def stream_answer(self, request):
        self.request = request
        if False:  # pragma: no cover - makes this an async generator
            yield {}


class _FakeMindMapService:
    def __init__(self) -> None:
        self.generated_with = None
        self.stored = {}

    async def generate(self, source_ids, refresh=False):
        ids = list(source_ids)
        self.generated_with = (ids, refresh)
        from app.mindmap.schemas import composite_key

        key = composite_key(ids)
        record = {
            "source_id": key,
            "source_ids": ids,
            "title": f"{len(ids)} sources",
            "markdown": "- root\n  - branch",
            "chunk_count": 3,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        self.stored[key] = record
        return record

    async def get(self, key):
        return self.stored.get(key)


@pytest.fixture
def client():
    query = _FakeQueryService()
    mindmap = _FakeMindMapService()
    app.dependency_overrides[get_query_service] = lambda: query
    app.dependency_overrides[get_mindmap_service] = lambda: mindmap
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_query_accepts_multiple_source_ids(client):
    async with client as c:
        response = await c.post(
            "/query",
            json={"question": "What changed?", "source_ids": ["a", "b"]},
        )
        assert response.status_code == 200
        assert response.json()["answer"] == "ok"


@pytest.mark.asyncio
async def test_query_without_source_ids_is_unscoped(client):
    async with client as c:
        response = await c.post("/query", json={"question": "Anything?"})
        assert response.status_code == 200
        assert response.json()["answer"] == "ok"


@pytest.mark.asyncio
async def test_query_accepts_no_sources_flag(client):
    async with client as c:
        response = await c.post(
            "/query",
            json={"question": "Tell me about source", "no_sources": True},
        )
        assert response.status_code == 200
        # The flag reaches the service verbatim so it can skip retrieval.
        assert response.json()["answer"] == "ok"


@pytest.mark.asyncio
async def test_query_stream_accepts_multiple_source_ids(client):
    async with (
        client as c,
        c.stream(
            "POST",
            "/query/stream",
            json={"question": "What changed?", "source_ids": ["a", "b"]},
        ) as response,
    ):
        assert response.status_code == 200
        async for _ in response.aiter_text():
            pass


# --------------------------------------------------------------------------- #
# Mind map
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_mindmap_generate_single_source_uses_the_legacy_field(client):
    async with client as c:
        response = await c.post(
            "/mindmap/generate",
            json={"source_id": "repo:owner/name"},
        )
        assert response.status_code == 201
        body = response.json()
        # A single source keeps its own id as the key so pre-existing cached
        # maps stay reachable.
        assert body["source_id"] == "repo:owner/name"
        assert body["source_ids"] == ["repo:owner/name"]


@pytest.mark.asyncio
async def test_mindmap_generate_multiple_sources_uses_a_composite_key(client):
    async with client as c:
        response = await c.post(
            "/mindmap/generate",
            json={"source_ids": ["doc:b", "repo:a/b"]},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_id"] == "multi:doc:b,repo:a/b"
        assert sorted(body["source_ids"]) == ["doc:b", "repo:a/b"]


@pytest.mark.asyncio
async def test_mindmap_selection_order_does_not_change_the_key(client):
    async with client as c:
        first = await c.post("/mindmap/generate", json={"source_ids": ["a", "b"]})
        second = await c.post("/mindmap/generate", json={"source_ids": ["b", "a"]})
        assert first.json()["source_id"] == second.json()["source_id"]


@pytest.mark.asyncio
async def test_mindmap_generate_requires_a_source(client):
    async with client as c:
        response = await c.post("/mindmap/generate", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_mindmap_get_fetches_by_composite_key(client):
    async with client as c:
        created = await c.post("/mindmap/generate", json={"source_ids": ["a", "b"]})
        key = created.json()["source_id"]
        fetched = await c.get(f"/mindmap/{key}")
        assert fetched.status_code == 200
        assert fetched.json()["source_id"] == key


@pytest.mark.asyncio
async def test_mindmap_get_unknown_key_is_404(client):
    async with client as c:
        response = await c.get("/mindmap/never-generated")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_mindmap_refresh_flag_is_forwarded(client):
    mindmap = _FakeMindMapService()
    app.dependency_overrides[get_mindmap_service] = lambda: mindmap
    async with client as c:
        await c.post("/mindmap/generate", json={"source_ids": ["a"], "refresh": True})
    assert mindmap.generated_with == (["a"], True)
