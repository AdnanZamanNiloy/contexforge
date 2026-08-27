"""Change-impact / blast-radius analysis for Repository Intelligence.

Given a selected file or module, we traverse the dependency graph (both
directions) up to *depth* hops and report the reachable surface: affected
files, modules, APIs, tests and dependencies.  The risk level is derived
from how large and distributed the blast radius is.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from observability.tracer import observe

__all__ = ["compute_change_impact"]

# Relationship kinds that propagate change.
_PROPAGATING = {"imports", "calls"}
_TEST_MARKERS = ("test_", "tests/", ".test.", "_test.")


@observe(name="repo_change_impact")
def compute_change_impact(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    selection_path: str,
    depth: int = 3,
) -> dict[str, Any]:
    """Compute the blast radius of a change to *selection_path*."""
    node_by_path = {n.get("path") or n.get("label"): n for n in nodes}
    node_by_id = {n["id"]: n for n in nodes}
    selected = node_by_path.get(selection_path)
    if selected is None:
        raise ValueError(f"'{selection_path}' is not a known node path")

    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for e in edges:
        if e.get("kind") not in _PROPAGATING:
            continue
        adjacency.setdefault(e["source"], []).append((e["target"], e))
        adjacency.setdefault(e["target"], []).append((e["source"], e))

    reached_ids: set[str] = {selected["id"]}
    reached_edges: dict[str, dict[str, Any]] = {}
    direct_ids: set[str] = {selected["id"]}
    frontier: deque[tuple[str, int]] = deque([(selected["id"], 0)])
    while frontier:
        cur, d = frontier.popleft()
        if d >= depth:
            continue
        for nxt, edge in adjacency.get(cur, ()):
            key = frozenset((edge["source"], edge["target"], edge["kind"]))
            reached_edges[key] = edge
            if nxt not in reached_ids:
                reached_ids.add(nxt)
                if d == 0:
                    direct_ids.add(nxt)
                frontier.append((nxt, d + 1))

    affected_nodes = [node_by_id[nid] for nid in reached_ids if nid in node_by_id]
    affected_nodes.sort(key=lambda n: n["id"])

    files = [n for n in affected_nodes if n.get("kind") == "file"]
    modules = [n for n in affected_nodes if n.get("kind") in {"module", "area"}]
    apis = [
        n
        for n in affected_nodes
        if n.get("kind") in {"route", "service"}
        or any(marker in (n.get("path", "")) for marker in ("routes/", "services/"))
        or n.get("path", "").endswith(".py")
    ]
    tests = [
        n
        for n in affected_nodes
        if any(marker in n.get("path", "") for marker in _TEST_MARKERS)
        or n.get("path", "").startswith("tests/")
        or n.get("path", "").startswith("test_")
    ]
    deps_total = sum(n.get("deps", 0) for n in affected_nodes)

    est = {
        "affected_files": len(files),
        "affected_modules": len(modules),
        "affected_apis": len(apis),
        "affected_tests": len(tests),
        "affected_dependencies": deps_total,
    }

    breadth = len(affected_nodes)
    risk = _severity(breadth, est["affected_dependencies"])
    nodes_out = []
    for n in affected_nodes:
        nodes_out.append(
            {
                "id": n["id"],
                "label": n.get("path") or n.get("label", ""),
                "kind": n.get("kind", "file"),
                "files": n.get("files", 0),
                "modules": 1 if n.get("kind") in {"module", "area"} else 0,
                "apis": 1 if n.get("kind") in {"route", "service"} else 0,
                "tests": 1 if any(marker in n.get("path", "") for marker in _TEST_MARKERS) else 0,
                "deps": n.get("deps", 0),
                "risk": n.get("risk", "Low"),
                "direct": n["id"] in direct_ids,
            }
        )

    edges_out = sorted(reached_edges.values(), key=lambda e: (e["source"], e["target"]))

    return {
        "selection": selection_path,
        "estimated": est,
        "risk": risk,
        "blast_radius": {"nodes": nodes_out, "edges": edges_out},
        "nodes": nodes_out,
    }


def _severity(breadth: int, deps: int) -> str:
    score = min(100.0, breadth * 2.5 + deps * 1.5)
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
