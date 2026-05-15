import json

import pytest
import httpx

from app.dependencies import get_ingest_service, get_query_service
from app.main import app


class FakeIngestService:
    async def ingest_source(self, request):
        return "source-123", 3

    async def ingest_file(self, source_type, content, filename):
        return "source-456", 2


class FakeQueryService:
    async def answer(self, request):
        return "hello world"

    async def stream_answer(self, request):
        yield "data: {\"type\": \"token\", \"token\": \"hi\"}\n\n"
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
