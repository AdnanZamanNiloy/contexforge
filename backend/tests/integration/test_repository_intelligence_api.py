"""Integration test for the Repository Intelligence HTTP API.

Uses a real local git fixture as the repo source (no network) and drives the
FastAPI app with ``TestClient``.  The analysis was started in the background,
so we poll the status endpoint until it completes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.main import app

try:
    from fastapi.testclient import TestClient

    _HAS_TESTCLIENT = True
except Exception:  # pragma: no cover - optional
    _HAS_TESTCLIENT = False


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="fastapi TestClient unavailable")
def test_repository_analyze_and_read_views(sample_repo: Path, analysis_dir: Path, monkeypatch):
    from app.dependencies import get_repository_store

    monkeypatch.setenv("VALIDATE_ON_START", "false")
    get_repository_store.cache_clear()
    with TestClient(app) as client:
        resp = client.post("/repository/analyze", json={"repo_url": str(sample_repo)})
        assert resp.status_code == 202
        payload = resp.json()
        analysis_id = payload["analysis_id"]
        assert analysis_id

        # Poll until the background analysis completes.
        status = None
        for _ in range(60):
            s = client.get(f"/repository/{analysis_id}/status").json()
            status = s
            if s["status"] in {"complete", "failed"}:
                break
            import time

            time.sleep(0.1)
        assert status["status"] == "complete", status

        bundle = client.get(f"/repository/{analysis_id}").json()
        assert bundle["repository"]["fullName"]
        assert bundle["architecture"]["nodes"]
        assert bundle["ownership"]["contributors"]

        arch = client.get(f"/repository/{analysis_id}/architecture").json()
        assert arch["nodes"]
        assert arch["edges"]

        dep = client.get(f"/repository/{analysis_id}/dependencies").json()
        assert dep["nodes"] is not None

        ci = client.get(
            f"/repository/{analysis_id}/change-impact",
            params={"path": "app/services/query_service.py"},
        ).json()
        assert ci["selection"] == "app/services/query_service.py"
        assert ci["estimated"]["affectedFiles"] > 0

        node = client.get(
            f"/repository/{analysis_id}/node",
            params={"node_id": "app/services/query_service.py"},
        ).json()
        assert node["type"] == "file"

        data_flow = client.get(f"/repository/{analysis_id}/data-flow").json()
        assert isinstance(data_flow, dict)


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="fastapi TestClient unavailable")
def test_repository_analyze_rejects_invalid_url(monkeypatch):
    from app.dependencies import get_repository_store

    monkeypatch.setenv("VALIDATE_ON_START", "false")
    get_repository_store.cache_clear()
    with TestClient(app) as client:
        resp = client.post("/repository/analyze", json={"repo_url": "not-a-repo"})
        assert resp.status_code == 422
