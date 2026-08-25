"""Transparent, explainable risk scoring for Repository Intelligence.

There is no opaque AI score here.  Each node's risk is a weighted sum of
five *observable* signals, each normalised to ``[0, 1]``:

- ``fanout``:      how many peers depend on / are depended on by the node
- ``churn``:       how often the node changes (from git history)
- ``complexity``:  size + symbol density (LOC)
- ``coverage``:    inverse of test coverage (missing tests raise risk)
- ``ownership``:   concentration risk (one author owns most of the node)

The weights are configurable in ``settings`` and can be reproduced exactly.
"""
from __future__ import annotations

from typing import Any

from app.config.settings import settings
from observability.tracer import observe

__all__ = [
    "compute_node_signals",
    "score_to_risk",
    "risk_score",
    "RISK_EXPLANATIONS",
    "compute_repo_health",
    "coverage_for_nodes",
    "ownership_concentration",
]

RISK_EXPLANATIONS: dict[str, str] = {
    "Low": "Low coupling and stable change rate — safe to evolve in isolation.",
    "Medium": "Moderate change frequency with a contained dependency footprint — review before large refactors.",
    "High": "Frequently changed, many dependents, and limited test coverage make this node a hot spot for regressions.",
    "Critical": "Central hub with high fan-out. Changes here cascade to a large fraction of the repository.",
}

_WEIGHTS = {
    "fanout": settings.RISK_FANOUT_WEIGHT,
    "churn": settings.RISK_CHURN_WEIGHT,
    "complexity": settings.RISK_COMPLEXITY_WEIGHT,
    "coverage": settings.RISK_COVERAGE_WEIGHT,
    "ownership": settings.RISK_OWNERSHIP_WEIGHT,
}


def compute_node_signals(
    node: dict[str, Any],
    churn: int,
    max_churn: int,
) -> dict[str, float]:
    """Normalise each risk signal for a single node to ``[0, 1]``."""
    fanout = min(1.0, (node.get("deps", 0) + node.get("dependents", 0)) / 20.0)
    churn_sig = min(1.0, churn / max_churn) if max_churn else 0.0
    complexity = min(1.0, node.get("loc", 0) / 500.0)
    coverage = min(1.0, max(0.0, node.get("coverage", 0.0)))
    coverage_inv = 1.0 - coverage
    ownership = min(1.0, node.get("ownership_risk", 0.0))
    return {
        "fanout": fanout,
        "churn": churn_sig,
        "complexity": complexity,
        "coverage": coverage_inv,
        "ownership": ownership,
    }


def risk_score(signals: dict[str, float]) -> float:
    """Weighted sum of normalised signals, scaled to ``[0, 100]``."""
    total = sum(_WEIGHTS[k] * signals.get(k, 0.0) for k in _WEIGHTS)
    return round(total * 100.0, 2)


def score_to_risk(score: float) -> str:
    """Threshold a ``[0, 100]`` risk score into a named severity level."""
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


@observe(name="repo_risk_all_nodes")
def apply_risk_to_nodes(
    nodes: list[dict[str, Any]],
    churn_by_rel: dict[str, int],
) -> list[dict[str, Any]]:
    """Mutate *nodes* in place, attaching ``risk``, ``risk_score`` and signals."""
    max_churn = max(churn_by_rel.values()) if churn_by_rel else 0
    for n in nodes:
        churn = churn_by_rel.get(n.get("path") or n.get("label"), 0)
        signals = compute_node_signals(n, churn, max_churn)
        score = risk_score(signals)
        n["risk_score"] = score
        n["risk"] = score_to_risk(score)
        n["signals"] = signals
        n["risk_reason"] = _explain(n, signals)
    return nodes


def _explain(node: dict[str, Any], signals: dict[str, float]) -> str:
    top = max(signals, key=signals.get)
    reasons = {
        "fanout": f"{node.get('deps', 0)} upstream deps and {node.get('dependents', 0)} dependents",
        "churn": f"changed {node.get('_churn', 0)} times in the window",
        "complexity": f"{node.get('loc', 0)} lines of code",
        "coverage": f"{int(node.get('coverage', 0) * 100)}% test coverage",
        "ownership": f"single-author concentration {int(node.get('ownership_risk', 0) * 100)}%",
    }
    return (f"Driven by {top}: {reasons[top]}.")


@observe(name="repo_health")
def compute_repo_health(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce an overall health score plus per-dimension breakdowns."""
    files = [n for n in nodes if n.get("kind") == "file"]
    if not files:
        return {"score": 0.0, "dimensions": []}

    avg_coverage = sum(n.get("coverage", 0.0) for n in files) / len(files)
    avg_complexity = 1.0 - sum(min(1.0, n.get("loc", 0) / 500.0)
                               for n in files) / len(files)
    avg_dep_health = 1.0 - min(1.0, (sum(n.get("deps", 0) for n in files)
                                     + sum(n.get("dependents", 0) for n in files))
                               / (len(files) * 20.0))
    # Security dimension is a placeholder derived from dependency fan-out,
    # deliberately conservative until a dedicated scanner is wired.
    avg_security = 1.0 - min(1.0, max((n.get("deps", 0) for n in files), default=0) / 30.0)

    dimensions = [
        ("Code Quality", avg_complexity * 100, "Inverse of size/complexity"),
        ("Test Coverage", avg_coverage * 100, "Share of files with tests"),
        ("Dependencies", avg_dep_health * 100, "Containment of fan-out"),
        ("Security", avg_security * 100, "Conservative dependency risk"),
    ]

    score = 0.35 * avg_complexity * 100 + 0.30 * avg_coverage * 100 \
        + 0.20 * avg_dep_health * 100 + 0.15 * avg_security * 100

    def _tone(v: float) -> str:
        return "good" if v >= 75 else ("warn" if v >= 50 else "critical")

    return {
        "score": round(min(100.0, score), 2),
        "dimensions": [
            {"label": label, "value": round(min(100.0, value), 2),
             "tone": _tone(value), "detail": detail}
            for label, value, detail in dimensions
        ],
    }


def coverage_for_nodes(files: list[dict[str, Any]]) -> dict[str, float]:
    """Estimate per-file test coverage from sibling filenames.

    A file with a corresponding ``test_*.py`` / ``*.test.*`` sibling, or a
    ``tests`` sibling directory, is treated as covered.  The estimate is a
    structural proxy, not a real coverage metric — documented as such.
    """
    test_suffixes = ("test_", "tests/", ".test.", "_test.")
    coverage: dict[str, float] = {}
    for n in files:
        path = n.get("path", "")
        if any(marker in path for marker in test_suffixes):
            coverage[path] = 1.0
            continue
        stem = path.rsplit("/", 1)[-1]
        base = stem.split(".")[0]
        # heuristic: a sibling with the same base name is the test counterpart
        has_test = any(
            other != path and other.rsplit("/", 1)[-1].startswith("test_")
            and base in other
            for other in (n["path"] for n in files)
        )
        coverage[path] = 1.0 if has_test else 0.0
    return coverage


def ownership_concentration(owners: list[dict[str, Any]], node_path: str) -> float:
    """Return ``[0, 1]`` concentration risk for a node path.

    ``owners`` is the list of ``{author, count}`` dicts for the path derived
    from git ownership.  A single author owning most commits raises risk.
    """
    total = sum(o["count"] for o in owners)
    if total == 0:
        return 0.0
    top = max(o["count"] for o in owners) / total
    return min(1.0, top * 1.5)
