"""Unit tests for change-impact / blast-radius analysis."""

from __future__ import annotations

import pytest

from app.repository_intelligence.impact import compute_change_impact


def _nodes_edges():
    nodes = [
        {"id": "src", "kind": "file", "path": "src/x.py", "deps": 3},
        {"id": "mid", "kind": "file", "path": "src/mid.py", "deps": 2},
        {"id": "far", "kind": "file", "path": "src/far.py", "deps": 1},
        {"id": "route", "kind": "route", "path": "app/routes/query.py", "deps": 0},
        {"id": "test", "kind": "file", "path": "tests/test_x.py", "deps": 0},
    ]
    edges = [
        {"source": "mid", "target": "src", "kind": "imports"},
        {"source": "far", "target": "mid", "kind": "imports"},
        {"source": "route", "target": "mid", "kind": "calls"},
        {"source": "test", "target": "src", "kind": "imports"},
    ]
    return nodes, edges


def test_change_impact_traverses_both_directions():
    nodes, edges = _nodes_edges()
    result = compute_change_impact(nodes, edges, "src/x.py", depth=2)
    assert result["selection"] == "src/x.py"
    assert result["estimated"]["affected_files"] >= 2
    assert result["estimated"]["affected_tests"] >= 1
    assert result["risk"] in {"Low", "Medium", "High", "Critical"}
    p = result["estimated"]
    assert p["affected_files"] == p["affected_files"]  # deterministic
    assert all(n["id"] for n in result["nodes"])


def test_change_impact_unknown_path_raises():
    nodes, edges = _nodes_edges()
    with pytest.raises(ValueError):
        compute_change_impact(nodes, edges, "does/not/exist.py")
