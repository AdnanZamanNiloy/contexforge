"""Unit tests for the SQLite RepositoryStore."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.repository_intelligence.storage import RepositoryStore


def _run_payload(run_id="r1", owner="o", name="n"):
    return {
        "id": run_id, "owner": owner, "name": name, "full_name": f"{owner}/{name}",
        "repo_url": "https://github.com/o/n", "branch": "main", "commit": "abc123",
        "status": "running", "progress": 10, "incremental": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_create_and_get_run(tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    await store.create_run(_run_payload())
    run = await store.get_run("r1")
    assert run is not None
    assert run["status"] == "running"
    assert run["commit_sha"] == "abc123"
    store.close()


@pytest.mark.asyncio
async def test_update_run_fields(tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    await store.create_run(_run_payload())
    await store.update_run("r1", status="complete", progress=100)
    run = await store.get_run("r1")
    assert run["status"] == "complete"
    assert run["progress"] == 100
    store.close()


@pytest.mark.asyncio
async def test_save_and_read_nodes_edges(tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    await store.create_run(_run_payload())
    nodes = [
        {"id": "repo", "label": "n", "kind": "repo", "path": "/", "files": 1,
         "loc": 3, "deps": 0, "dependents": 0, "risk": "Low", "risk_score": 1,
         "coverage": 0.0, "x": None, "y": None, "meta": {"commit": "abc123"},
         "signals": {}},
        {"id": "f1", "label": "f.py", "kind": "file", "path": "f.py", "files": 1,
         "loc": 3, "deps": 0, "dependents": 0, "risk": "Medium", "risk_score": 50,
         "coverage": 1.0, "x": 100.0, "y": 200.0, "meta": {}, "signals": {"churn": 1}},
    ]
    edges = [{"source": "f1", "target": "repo", "kind": "imports",
              "relationship_source": "ast", "confidence": 1.0}]
    await store.save_analysis("r1", nodes, edges, '{"k": 1}')
    read_nodes = await store.get_nodes("r1")
    read_edges = await store.get_edges("r1")
    assert len(read_nodes) == 2
    f1 = next(n for n in read_nodes if n["id"] == "f1")
    assert f1["signals"]["churn"] == 1
    assert f1["coverage"] == 1.0
    assert len(read_edges) == 1
    assert read_edges[0]["relationship_source"] == "ast"
    store.close()


@pytest.mark.asyncio
async def test_save_marks_run_complete_with_commit(tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    await store.create_run(_run_payload())
    nodes = [{"id": "repo", "kind": "repo", "path": "/",
              "meta": {"commit": "deadbeef"}}]
    await store.save_analysis("r1", nodes, [], "{}")
    run = await store.get_run("r1")
    assert run["status"] == "complete"
    assert run["commit_sha"] == "deadbeef"
    store.close()


@pytest.mark.asyncio
async def test_latest_run_ordering(tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    await store.create_run(_run_payload("r-old", owner="o", name="n"))
    await store.update_run("r-old", status="complete", commit_sha="aaa111")
    later = _run_payload("r-new", owner="o", name="n")
    later["created_at"] = datetime.now(timezone.utc).isoformat()
    await store.create_run(later)
    await store.update_run("r-new", status="complete", commit_sha="bbb222")
    latest = await store.get_latest_run("o", "n")
    assert latest["id"] == "r-new"
    assert latest["commit_sha"] == "bbb222"
    store.close()


@pytest.mark.asyncio
async def test_incremental_reuse_same_commit(sample_repo, tmp_path: Path):
    """Running twice for the same commit is idempotent at the service layer."""
    from app.repository_intelligence.analyzer import RepositoryAnalyzer
    from app.repository_intelligence.service import RepositoryIntelligenceService

    store = RepositoryStore(db_path=tmp_path / "ri.db")
    svc = RepositoryIntelligenceService(store, RepositoryAnalyzer())
    first = await svc.run_analysis("r1", str(sample_repo))
    assert first["incremental"] is False
    second = await svc.run_analysis("r2", str(sample_repo))
    assert second["incremental"] is True
    store.close()
