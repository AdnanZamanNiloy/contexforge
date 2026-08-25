"""Dependency analysis for Repository Intelligence.

Computes per-node fan-out (``deps`` = outbound edges, ``dependents`` =
inbound edges) and infers ``calls`` edges from qualified-name usage.  Every
edge keeps a ``relationship_source`` and ``confidence`` so claims are
traceable back to the evidence.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from typing import Any

from observability.tracer import observe

__all__ = [
    "enrich_nodes_with_degree",
    "derive_calls",
    "ranked_modules",
    "build_dependency_subgraph",
    "dependents_of",
    "dependencies_of",
]

_CALL_RE = re.compile(r"\b([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\(")


@observe(name="repo_dependency_degree")
def enrich_nodes_with_degree(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return nodes with ``deps`` (out) and ``dependents`` (in) counts."""
    deps: dict[str, int] = defaultdict(int)
    dependents: dict[str, int] = defaultdict(int)
    for e in edges:
        if e.get("kind") == "contains":
            continue
        deps[e["source"]] += 1
        dependents[e["target"]] += 1

    out: list[dict[str, Any]] = []
    for n in nodes:
        nid = n["id"]
        n["deps"] = deps.get(nid, 0)
        n["dependents"] = dependents.get(nid, 0)
        out.append(n)
    return out


@observe(name="repo_dependency_calls")
def derive_calls(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    ns_to_node: dict[str, str],
    files_by_rel: dict[str, str],
) -> list[dict[str, Any]]:
    """Infer ``calls`` edges from qualified call usage in source files.

    For each Python file, we look for ``alias.symbol(...)`` and record a
    ``calls`` edge when ``alias`` imports a module that resolves to a file
    node.  Confidence is < 1.0 because this is an inference, not a full
    cross-module call graph.
    """
    calls: list[dict[str, Any]] = []
    for n in nodes:
        if n.get("kind") != "file":
            continue
        rel = n["path"]
        text = files_by_rel.get(rel)
        if not text or not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                used.add(f"{node.func.value.id}.{node.func.attr}" if isinstance(node.func.value, ast.Name) else "")
        if not used:
            continue
        # Map each module alias imported by this file to a target node.
        imported: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.setdefault(alias.asname or alias.name.split(".")[0], alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported.setdefault(alias.asname or alias.name, f"{node.module}.{alias.name}")
        for qualified in used:
            if not qualified:
                continue
            alias, _symbol = qualified.split(".", 1)
            spec = imported.get(alias)
            if not spec:
                continue
            target = _resolve_spec(spec, ns_to_node)
            if target and target != n["id"]:
                calls.append({
                    "source": n["id"], "target": target, "kind": "calls",
                    "relationship_source": "ast", "confidence": 0.7,
                })
    return calls


def _resolve_spec(spec: str, ns_to_node: dict[str, str]) -> str | None:
    if spec in ns_to_node:
        return ns_to_node[spec]
    parts = spec.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in ns_to_node:
            return ns_to_node[candidate]
    return None


@observe(name="repo_dependency_rank")
def ranked_modules(
    nodes: list[dict[str, Any]], top: int = 5
) -> list[dict[str, Any]]:
    """Rank modules/files by dependency weight (deps + dependents)."""
    weighted = [
        {
            "name": n["path"] or n["label"],
            "value": min(100.0, (n.get("deps", 0) + n.get("dependents", 0)) * 3.0),
            "reason": (f"{n.get('deps', 0)} upstream deps, "
                       f"{n.get('dependents', 0)} dependents"),
        }
        for n in nodes
        if n.get("kind") in {"module", "area", "file"} and n.get("path")
    ]
    weighted.sort(key=lambda w: w["value"], reverse=True)
    return weighted[:top]


@observe(name="repo_dependency_subgraph")
def build_dependency_subgraph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    center_id: str,
    depth: int = 2,
) -> dict[str, Any]:
    """Return nodes/edges within *depth* hops of *center_id* (non-contains edges)."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.get("kind") == "contains":
            continue
        adjacency[e["source"]].add(e["target"])
        adjacency[e["target"]].add(e["source"])

    node_by_id = {n["id"]: n for n in nodes}
    visited_nodes: set[str] = {center_id}
    visited_edge_keys: set[tuple[str, str]] = set()
    frontier: list[tuple[str, int]] = [(center_id, 0)]
    while frontier:
        cur, d = frontier.pop()
        if d >= depth:
            continue
        for nxt in adjacency.get(cur, ()):
            pairs = tuple(sorted((cur, nxt)))
            if pairs in visited_edge_keys:
                continue
            visited_edge_keys.add(pairs)
            if nxt not in visited_nodes:
                visited_nodes.add(nxt)
                frontier.append((nxt, d + 1))

    seen: set[tuple[str, str, str]] = set()
    visited_edges: list[dict[str, Any]] = []
    for e in edges:
        if e.get("kind") == "contains":
            continue
        if e["source"] in visited_nodes and e["target"] in visited_nodes:
            key = (e["source"], e["target"], e["kind"])
            if key not in seen:
                seen.add(key)
                visited_edges.append(e)

    sub_nodes = [node_by_id[nid] for nid in visited_nodes if nid in node_by_id]
    return {"nodes": sub_nodes, "edges": visited_edges}


def dependents_of(nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                  node_id: str) -> list[str]:
    return [e["source"] for e in edges if e["target"] == node_id]


def dependencies_of(nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                    node_id: str) -> list[str]:
    return [e["target"] for e in edges if e["source"] == node_id]
