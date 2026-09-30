"""HTTP tests for ``POST /context/estimate``.

The endpoint's job is to report the cost of a selection honestly, including the
sources it cannot use.  A fake orchestrator stands in for the real one so no
vector store, embedding call or provider request is involved.
"""

from __future__ import annotations

import httpx
import pytest

from app.dependencies import get_orchestrator
from app.main import app


def _chunk(source_id, index, text="x" * 200, **metadata):
    from types import MappingProxyType

    return type(
        "FakeChunk",
        (),
        {
            "chunk_id": f"{source_id}:{index}",
            "text": text,
            "metadata": MappingProxyType({"source_id": source_id, **metadata}),
            "source_id": source_id,
        },
    )()


class _FakeFaiss:
    def __init__(self, chunks):
        self._chunks = chunks

    async def get_chunks_by_source_id(self, source_id):
        if not source_id:
            return list(self._chunks)
        return [c for c in self._chunks if c.source_id == source_id]


def _orchestrator(chunks):
    orch = type("Orch", (), {})()
    orch._faiss = _FakeFaiss(chunks)
    return orch


@pytest.fixture
def client():
    chunks = [
        *[_chunk("a", i, "a" * 300) for i in range(5)],
        *[_chunk("b", i, "b" * 300) for i in range(5)],
        *[_chunk("c", i, "c" * 300) for i in range(40)],
    ]
    app.dependency_overrides[get_orchestrator] = lambda: _orchestrator(chunks)
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_prices_a_selection(client):
    async with client as c:
        response = await c.post("/context/estimate", json={"source_ids": ["a"]})

        assert response.status_code == 200
        body = response.json()
        assert body["source_count"] == 1
        assert body["sources"][0]["source_id"] == "a"
        assert body["total_token_count"] > 0


@pytest.mark.asyncio
async def test_reports_available_versus_used(client):
    async with client as c:
        body = (await c.post("/context/estimate", json={"source_ids": ["a", "b", "c"]})).json()

        # The gap is the point: the selection is far larger than the prompt.
        assert body["total_token_count"] > body["prompt_token_estimate"]
        assert 0 < body["usable_fraction"] < 1
        assert body["prompt_chunk_limit"] == 5


@pytest.mark.asyncio
async def test_depth_changes_what_reaches_the_model(client):
    async with client as c:
        payload = {"source_ids": ["a", "b", "c"]}
        focused = (await c.post("/context/estimate", json={**payload, "depth": "focused"})).json()
        broad = (await c.post("/context/estimate", json={**payload, "depth": "broad"})).json()

        assert broad["prompt_token_estimate"] > focused["prompt_token_estimate"]
        assert broad["prompt_chunk_limit"] > focused["prompt_chunk_limit"]


@pytest.mark.asyncio
async def test_broad_over_a_single_source_is_honoured(client):
    async with client as c:
        body = (await c.post("/context/estimate", json={"source_ids": ["a"], "depth": "broad"})).json()

        # One source is the case where widening must work: the per-source caps
        # exist to stop sources crowding each other out, which cannot happen with
        # a single document, so reducing the depth here left the control inert.
        assert body["depth"] == "broad"
        assert body["effective_depth"] == "broad"
        assert body["per_source_cap"] > 5


@pytest.mark.asyncio
async def test_defaults_to_the_whole_knowledge_base(client):
    async with client as c:
        body = (await c.post("/context/estimate", json={})).json()

        assert body["source_count"] == 3


@pytest.mark.asyncio
async def test_names_dropped_and_missing_sources(client):
    async with client as c:
        body = (
            await c.post(
                "/context/estimate",
                json={"source_ids": ["a", "b", "c", "ghost"], "depth": "focused"},
            )
        ).json()

        assert body["missing_source_ids"] == ["ghost"]
        assert len(body["dropped_source_ids"]) >= 1
        # A missing source is not silently counted as available.
        assert body["source_count"] == 3


@pytest.mark.asyncio
async def test_rejects_an_unknown_depth(client):
    async with client as c:
        response = await c.post("/context/estimate", json={"depth": "ludicrous"})

        assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_store_failure_becomes_a_500(client):
    class _BrokenFaiss:
        async def get_chunks_by_source_id(self, source_id):
            raise RuntimeError("store offline")

    orch = type("Orch", (), {"_faiss": _BrokenFaiss()})()
    app.dependency_overrides[get_orchestrator] = lambda: orch
    async with client as c:
        response = await c.post("/context/estimate", json={"source_ids": ["a"]})

        assert response.status_code == 500
        assert "store offline" in response.json()["detail"]
