"""HTTP contract tests for per-source Studio tool selection.

Verifies that the analysis routes accept an explicit ``source_id``, pass it
through to the service, and reject a source that is not part of the project —
plus that the project remembers the chosen tool source.
"""

from __future__ import annotations

import httpx
import pytest

from app.dependencies import get_ingest_service, get_techstack_service
from app.main import app


class _FakeIngest:
    class _Orchestrator:
        class _Faiss:
            async def get_source_info(self):
                return [
                    {"source_id": "repo:a/x", "type": "github", "title": "a/x", "metadata": {"repo": "a/x"}},
                    {"source_id": "repo:b/y", "type": "github", "title": "b/y", "metadata": {"repo": "b/y"}},
                ]

        _faiss = _Faiss()

    _orchestrator = _Orchestrator()


class _FakeTechStack:
    def __init__(self):
        self.calls = []

    async def get(self, project_id, source_id=""):
        _ = project_id, source_id
        return None

    async def scan(self, project_id, source_id, *, refresh=False):
        self.calls.append((project_id, source_id, refresh))
        return {
            "source_id": source_id,
            "repository": source_id,
            "summary": "ok",
            "language_count": 1,
        }


@pytest.fixture
def client():
    techstack = _FakeTechStack()
    app.dependency_overrides[get_techstack_service] = lambda: techstack
    app.dependency_overrides[get_ingest_service] = lambda: _FakeIngest()
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test"), techstack
    app.dependency_overrides.clear()


async def _project(c, name="Tools", source_ids=("repo:a/x", "repo:b/y")):
    project_id = (await c.post("/projects", json={"name": name})).json()["id"]
    for sid in source_ids:
        await c.post(f"/projects/{project_id}/sources", json={"source_id": sid})
    return project_id


@pytest.mark.asyncio
async def test_scan_honours_an_explicit_source(client):
    c, techstack = client
    async with c:
        pid = await _project(c)
        response = await c.post(
            "/tech-stack/scan",
            json={"project_id": pid, "source_id": "repo:b/y"},
        )
        assert response.status_code == 200
        assert response.json()["source_id"] == "repo:b/y"
        assert techstack.calls[-1][1] == "repo:b/y"


@pytest.mark.asyncio
async def test_scan_falls_back_to_first_github_source(client):
    c, techstack = client
    async with c:
        pid = await _project(c)
        response = await c.post("/tech-stack/scan", json={"project_id": pid})
        assert response.status_code == 200
        assert techstack.calls[-1][1] == "repo:a/x"


@pytest.mark.asyncio
async def test_scan_rejects_a_source_outside_the_project(client):
    c, _ = client
    async with c:
        pid = await _project(c)
        response = await c.post(
            "/tech-stack/scan",
            json={"project_id": pid, "source_id": "repo:not/mine"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_project_remembers_the_tool_source():
    # Uses the real projects service/store (isolated to tmp_path by the fixture).
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        pid = await _project(c, name="Remember", source_ids=("repo:a/x",))
        updated = await c.put(f"/projects/{pid}/tool-source", json={"source_id": "repo:a/x"})
        assert updated.status_code == 200
        assert updated.json()["tool_source_id"] == "repo:a/x"

        fetched = await c.get(f"/projects/{pid}")
        assert fetched.json()["tool_source_id"] == "repo:a/x"


@pytest.mark.asyncio
async def test_remembered_source_is_used_when_request_omits_it(client):
    c, techstack = client
    async with c:
        pid = await _project(c)
        # Remember the second source, then scan without an explicit one: the
        # resolver must prefer the remembered source over the first GitHub one.
        await c.put(f"/projects/{pid}/tool-source", json={"source_id": "repo:b/y"})
        response = await c.post("/tech-stack/scan", json={"project_id": pid})
        assert response.status_code == 200
        assert techstack.calls[-1][1] == "repo:b/y"
