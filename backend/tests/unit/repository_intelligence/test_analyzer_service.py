"""End-to-end unit test for the Repository Intelligence analyzer + service,
driven by a real local git fixture (no network)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.repository_intelligence.analyzer import RepositoryAnalyzer
from app.repository_intelligence.service import RepositoryIntelligenceService
from app.repository_intelligence.storage import RepositoryStore


@pytest.mark.asyncio
async def test_full_analysis_bundle(sample_repo: Path, tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    svc = RepositoryIntelligenceService(store, RepositoryAnalyzer())

    result = await svc.run_analysis("full-run", str(sample_repo))
    assert result["incremental"] is False
    assert result["commit"]

    status = await svc.get_status("full-run")
    assert status.status == "complete"
    assert status.progress == 100

    bundle = await svc.get_analysis("full-run")
    assert bundle.repository.files == 5
    assert bundle.repository.language == "Python"
    assert len(bundle.architecture.nodes) >= 6
    assert any(e.kind == "imports" for e in bundle.architecture.edges)
    assert bundle.health is not None and 0 < bundle.health.score < 100
    assert bundle.ownership.contributors
    assert bundle.git_history.commits
    # sample_repo has no HTTP/CLI entry point, so no executable flow is detected.
    assert bundle.data_flows == {}
    assert bundle.risk_explanations.Critical
    assert bundle.ranked_modules
    store.close()


@pytest.mark.asyncio
async def test_view_endpoints_roundtrip(sample_repo: Path, tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    svc = RepositoryIntelligenceService(store, RepositoryAnalyzer())
    await svc.run_analysis("r1", str(sample_repo))

    dep = await svc.get_dependencies("r1", None)
    assert dep.nodes
    assert dep.edges

    ci = await svc.get_change_impact("r1", "app/services/query_service.py")
    assert ci["selection"] == "app/services/query_service.py"
    assert ci["estimated"]["affected_files"] > 0

    details = await svc.get_module_details("r1", "app/services/query_service.py")
    assert details["type"] == "file"
    assert details["top_dependencies"]

    flows = await svc.get_data_flows("r1")
    # sample_repo has no runnable entry point — expect no executable flow.
    assert flows == {}
    store.close()


@pytest.mark.asyncio
async def test_detects_execution_flow(flow_repo: Path, tmp_path: Path):
    store = RepositoryStore(db_path=tmp_path / "ri.db")
    svc = RepositoryIntelligenceService(store, RepositoryAnalyzer())
    await svc.run_analysis("flow-run", str(flow_repo))

    flows = await svc.get_data_flows("flow-run")
    assert flows
    flow = next(iter(flows.values()))
    assert flow["title"] == "GET /query"
    assert flow["entry"] == "app/routes/query.py"
    assert len(flow["nodes"]) >= 3
    assert len(flow["edges"]) >= 2
    ids = {n["id"] for n in flow["nodes"]}
    assert any("services/query_service" in i for i in ids)
    assert any("core/storage" in i for i in ids)
    for b in flow["bottlenecks"]:
        assert b["latency_ms"] is None
    store.close()


@pytest.mark.asyncio
async def test_failed_run_records_error(tmp_path: Path, monkeypatch):
    from app.repository_intelligence.git import GitRepository

    store = RepositoryStore(db_path=tmp_path / "ri.db")
    svc = RepositoryIntelligenceService(store, RepositoryAnalyzer())

    async def failing_clone(self, *args, **kwargs):
        from app.repository_intelligence.git import GitRepoError
        raise GitRepoError("network unavailable")

    monkeypatch.setattr(GitRepository, "clone", failing_clone)

    # run_id without a pre-created row: _ensure_run creates it before clone runs.
    with pytest.raises(Exception):
        await svc.run_analysis("bad-run", "https://github.com/owner/repo")
    status = await svc.get_status("bad-run")
    assert status.status == "failed"
    store.close()
