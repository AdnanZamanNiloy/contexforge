"""Per-source keying for the Studio analysis tools.

Architecture/Security/Tech Stack/Health each analyse ONE source.  These tests
pin the two guarantees that make switching sources work:

- each source keeps its own stored output (writing one never touches another);
- the resolver picks the explicit source when given, else the project's
  remembered selection, else the first GitHub source — while Repo Chat, which is
  not a tool route, is unaffected.
"""

import pytest

from app.architecture.storage import ArchitectureStore
from app.health.storage import HealthStore
from app.projects.service import ProjectsService
from app.projects.source_resolution import (
    ResolvedSource,
    SourceResolutionError,
    resolve_tool_source,
)
from app.projects.store import ProjectsStore
from app.security.storage import SecurityStore
from app.techstack.storage import TechStackStore

# --------------------------------------------------------------------------- #
# Stores: output is isolated per (project, source)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_architecture_store_isolates_sources(tmp_path):
    store = ArchitectureStore(tmp_path / "arch.db")
    base = {"repository": "r", "mermaid": "flowchart TD", "explanation": "", "node_count": 1}

    await store.upsert("p1", "src-a", {**base, "fingerprint": "fa", "mermaid": "A"})
    await store.upsert("p1", "src-b", {**base, "fingerprint": "fb", "mermaid": "B"})

    assert (await store.latest("p1", "src-a"))["mermaid"] == "A"
    assert (await store.latest("p1", "src-b"))["mermaid"] == "B"
    # Rewriting one source must not disturb the other.
    await store.upsert("p1", "src-a", {**base, "fingerprint": "fa", "mermaid": "A2"})
    assert (await store.latest("p1", "src-a"))["mermaid"] == "A2"
    assert (await store.latest("p1", "src-b"))["mermaid"] == "B"


@pytest.mark.asyncio
async def test_health_store_isolates_sources(tmp_path):
    store = HealthStore(tmp_path / "health.db")
    await store.upsert("p1", "src-a", {"repository": "r", "health": 90}, "fa")
    await store.upsert("p1", "src-b", {"repository": "r", "health": 40}, "fb")
    assert (await store.latest("p1", "src-a"))["health"] == 90
    assert (await store.latest("p1", "src-b"))["health"] == 40


@pytest.mark.asyncio
async def test_techstack_store_isolates_sources(tmp_path):
    store = TechStackStore(tmp_path / "ts.db")
    await store.upsert("p1", "src-a", {"repository": "r", "language_count": 1}, "fa")
    await store.upsert("p1", "src-b", {"repository": "r", "language_count": 5}, "fb")
    assert (await store.latest("p1", "src-a"))["language_count"] == 1
    assert (await store.latest("p1", "src-b"))["language_count"] == 5


@pytest.mark.asyncio
async def test_security_store_isolates_sources(tmp_path):
    store = SecurityStore(db_path=tmp_path / "sec.db")
    await store.upsert("p1", "src-a", {"repository": "r", "finding_count": 2}, "fa")
    await store.upsert("p1", "src-b", {"repository": "r", "finding_count": 9}, "fb")
    assert (await store.latest("p1", "src-a"))["finding_count"] == 2
    assert (await store.latest("p1", "src-b"))["finding_count"] == 9


# --------------------------------------------------------------------------- #
# Resolver precedence
# --------------------------------------------------------------------------- #


def _inventory():
    return [
        {"source_id": "repo:a/x", "type": "github", "title": "a/x", "metadata": {"repo": "a/x"}},
        {"source_id": "repo:b/y", "type": "github", "title": "b/y", "metadata": {"repo": "b/y"}},
        {"source_id": "doc:notes", "type": "pdf", "title": "notes"},
    ]


async def _project_with(tmp_path, source_ids, tool_source_id=""):
    projects = ProjectsService(ProjectsStore(db_path=tmp_path / "projects.db"))
    project = await projects.create("P")
    for sid in source_ids:
        await projects.attach(project["id"], sid)
    if tool_source_id:
        await projects.set_tool_source(project["id"], tool_source_id)
    return projects, project["id"]


@pytest.mark.asyncio
async def test_explicit_source_wins(tmp_path):
    projects, pid = await _project_with(tmp_path, ["repo:a/x", "repo:b/y"])
    resolved = await resolve_tool_source(pid, "repo:b/y", projects, _inventory())
    assert resolved == ResolvedSource(source_id="repo:b/y", label="b/y")


@pytest.mark.asyncio
async def test_remembered_source_used_when_no_explicit(tmp_path):
    projects, pid = await _project_with(tmp_path, ["repo:a/x", "repo:b/y"], tool_source_id="repo:b/y")
    resolved = await resolve_tool_source(pid, None, projects, _inventory())
    assert resolved.source_id == "repo:b/y"


@pytest.mark.asyncio
async def test_first_github_source_is_the_default(tmp_path):
    projects, pid = await _project_with(tmp_path, ["doc:notes", "repo:b/y", "repo:a/x"])
    resolved = await resolve_tool_source(pid, None, projects, _inventory())
    assert resolved.source_id == "repo:b/y"


@pytest.mark.asyncio
async def test_explicit_source_outside_the_project_is_rejected(tmp_path):
    projects, pid = await _project_with(tmp_path, ["repo:a/x"])
    with pytest.raises(SourceResolutionError):
        await resolve_tool_source(pid, "repo:not/mine", projects, _inventory())


@pytest.mark.asyncio
async def test_unknown_project_is_rejected(tmp_path):
    projects, _ = await _project_with(tmp_path, ["repo:a/x"])
    with pytest.raises(SourceResolutionError):
        await resolve_tool_source("proj_missing", None, projects, _inventory())


@pytest.mark.asyncio
async def test_non_github_member_is_a_last_resort(tmp_path):
    projects, pid = await _project_with(tmp_path, ["doc:notes"])
    resolved = await resolve_tool_source(pid, None, projects, _inventory())
    assert resolved.source_id == "doc:notes"
