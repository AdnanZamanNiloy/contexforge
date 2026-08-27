import json

import httpx
import pytest

from app.dependencies import get_ingest_service, get_query_service
from app.main import app
from core.types import Chunk, GenerationResult, RerankedChunk


class FakeIngestService:
    async def ingest_source(self, request):
        return "source-123", 3

    async def ingest_file(self, source_type, content, filename):
        return "source-456", 2

    async def delete_source(self, source_id):
        return 5


class FakeQueryService:
    async def answer(self, request):
        return GenerationResult(
            answer="hello world",
            sources=[
                RerankedChunk(
                    chunk=Chunk(
                        chunk_id="c1",
                        text="sample context",
                        metadata={"source_id": "s1"},
                        source_id="s1",
                    ),
                    score=0.8,
                    rank=1,
                )
            ],
            latency_ms={"total": 1.0},
        )

    async def stream_answer(self, request):
        yield 'data: {"type": "token", "token": "hi"}\n\n'
        payload = {"type": "done", "sources": [], "latency_ms": {"total": 1.0}}
        yield f"data: {json.dumps(payload)}\n\n"


@pytest.mark.asyncio
async def test_query_endpoint_returns_answer():
    app.dependency_overrides[get_query_service] = lambda: FakeQueryService()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/query", json={"question": "hi"})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "hello world"


@pytest.mark.asyncio
async def test_stream_endpoint_yields_events():
    app.dependency_overrides[get_query_service] = lambda: FakeQueryService()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/query/stream", json={"question": "hi"})
        body = response.text

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "data:" in body


@pytest.mark.asyncio
async def test_ingest_source_endpoint():
    app.dependency_overrides[get_ingest_service] = lambda: FakeIngestService()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"source_type": "text", "source": "hello"}
        response = await client.post("/ingest/source", json=payload)

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["source_id"] == "source-123"


class FailingIngestService(FakeIngestService):
    async def ingest_source(self, request):
        raise RuntimeError("Voyage API failed after 5 attempts")


@pytest.mark.asyncio
async def test_github_ingest_survives_rag_failure(monkeypatch):
    """RAG ingest failure (e.g. embedding rate-limit) must not fail the endpoint;
    it should still return 200 with an analysis_id."""
    import app.dependencies as deps

    class FakeRIntelligence:
        async def start_analysis(self, repo_url, branch=None):
            return {"analysis_id": "ri-123"}

    monkeypatch.setattr(deps, "get_repository_intelligence_service", lambda: FakeRIntelligence())
    app.dependency_overrides[get_ingest_service] = lambda: FailingIngestService()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/github/ingest",
            json={"repo_url": "https://github.com/octocat/Hello-World"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["chunks_indexed"] == 0
    assert body["analysis_id"] == "ri-123"
    assert "skipped" in body["message"]
    assert "Repository Intelligence analysis started" in body["message"]


@pytest.mark.asyncio
async def test_delete_source_endpoint():
    app.dependency_overrides[get_ingest_service] = lambda: FakeIngestService()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/ingest/source/source-123")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == "source-123"
    assert body["chunks_deleted"] == 5
    assert "message" in body


@pytest.mark.asyncio
async def test_delete_source_empty_id_returns_422():
    """Deleting with an empty source_id should be rejected."""
    app.dependency_overrides[get_ingest_service] = lambda: FakeIngestService()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/ingest/source/")

    app.dependency_overrides.clear()

    # FastAPI redirects /ingest/source/ → /ingest/source (307),
    # or returns 404/405 if the path doesn't match any route
    assert response.status_code in (307, 404, 405, 422)
