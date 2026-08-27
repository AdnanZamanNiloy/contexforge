"""Unit tests for transparent risk scoring."""

from __future__ import annotations

import pytest

from app.repository_intelligence.risk import (
    RISK_EXPLANATIONS,
    apply_risk_to_nodes,
    compute_node_signals,
    compute_repo_health,
    coverage_for_nodes,
    ownership_concentration,
    risk_score,
    score_to_risk,
)


class TestScoring:
    def test_compute_node_signals_normalises(self):
        sig = compute_node_signals(
            {"deps": 10, "dependents": 10, "loc": 250, "coverage": 0.0, "ownership_risk": 1.0},
            churn=5,
            max_churn=10,
        )
        assert sig["fanout"] == pytest.approx(1.0)
        assert sig["churn"] == pytest.approx(0.5)
        assert sig["complexity"] == pytest.approx(0.5)
        assert sig["coverage"] == pytest.approx(1.0)
        assert sig["ownership"] == pytest.approx(1.0)

    def test_risk_score_is_weighted_sum(self):
        sig = {"fanout": 1.0, "churn": 0.0, "complexity": 0.0, "coverage": 0.0, "ownership": 0.0}
        assert risk_score(sig) == pytest.approx(30.0, abs=0.01)

    @pytest.mark.parametrize(
        "score,expected",
        [
            (10, "Low"),
            (45, "Medium"),
            (65, "High"),
            (90, "Critical"),
            (79, "High"),
            (80, "Critical"),
            (60, "High"),
            (40, "Medium"),
        ],
    )
    def test_score_to_risk_thresholds(self, score, expected):
        assert score_to_risk(score) == expected

    def test_risk_explanations_exist_for_all_levels(self):
        for level in ("Low", "Medium", "High", "Critical"):
            assert RISK_EXPLANATIONS[level]

    def test_apply_risk_to_nodes_attaches_reason(self):
        nodes = [
            {
                "id": "a",
                "kind": "file",
                "path": "a.py",
                "loc": 10,
                "deps": 0,
                "dependents": 0,
                "coverage": 1.0,
                "ownership_risk": 0.0,
            },
        ]
        out = apply_risk_to_nodes(nodes, churn_by_rel={"a.py": 0})
        assert out[0]["risk"] in {"Low", "Medium", "High", "Critical"}
        assert "Driven by" in out[0]["risk_reason"]


class TestCoverage:
    def test_detects_test_file(self):
        files = [
            {"path": "app/x.py"},
            {"path": "app/test_x.py"},
        ]
        cov = coverage_for_nodes(files)
        assert cov["app/x.py"] == 1.0
        assert cov["app/test_x.py"] == 1.0

    def test_uncovered_file(self):
        files = [{"path": "app/only.py"}]
        cov = coverage_for_nodes(files)
        assert cov["app/only.py"] == 0.0


class TestOwnershipConcentration:
    def test_single_author_high_concentration(self):
        assert ownership_concentration([{"count": 9}, {"count": 1}], "x.py") > 0.9

    def test_empty_returns_zero(self):
        assert ownership_concentration([], "x.py") == 0.0


class TestRepoHealth:
    def test_health_score_and_dimensions(self):
        nodes = [
            {"kind": "file", "loc": 50, "coverage": 1.0, "deps": 1, "dependents": 0},
            {"kind": "file", "loc": 50, "coverage": 0.0, "deps": 1, "dependents": 0},
        ]
        health = compute_repo_health(nodes)
        assert {"score", "dimensions"} <= set(health)
        assert 0 <= health["score"] <= 100
        labels = {d["label"] for d in health["dimensions"]}
        assert labels == {"Code Quality", "Test Coverage", "Dependencies", "Security"}

    def test_empty_repo_health(self):
        assert compute_repo_health([])["score"] == 0.0
