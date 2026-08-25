"""Execution / data-flow detection for Repository Intelligence.

Rather than inventing a fixed pipeline, we analyse the static code graph that
the analyzer already produced: HTTP route decorators, ``main``/CLI entry
points, cross-file ``imports`` and ``calls`` edges, plus the imports each file
makes of third-party packages (storage, external APIs, SDKs).  From those we
derive one directional graph per detected entry point.

Design rules:
  * every node/edge is grounded in a real repo-relative path or real import;
  * ``bottlenecks`` carry only code-measurable metrics (callers / dependents /
    LOC) — never fabricated durations.  ``latency_ms`` stays ``None`` unless a
    real measurement source is wired in later;
  * no fixed ContextForge pipeline; no repository-specific mock data.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict, deque
from typing import Any, Iterable

from observability.tracer import observe

__all__ = ["infer_data_flows"]

# Node kinds we surface in a flow.
_ENTRY_BASENAMES = {
    "app.py", "main.py", "__main__.py", "cli.py", "server.py", "manage.py",
    "wsgi.py", "asgi.py", "index.js", "index.ts", "index.jsx", "index.tsx",
    "routes.ts", "routes.js", "api.ts", "api.js", "server.js", "server.ts",
    "main.go", "main.rs", "main.java", "main.kt", "Program.cs", "index.php",
}
_ENTRY_DIR_PARTS = {
    "routes", "api", "endpoints", "controllers", "handlers", "views", "web",
    "cmd", "scripts", "cli", "gateway", "workers", "jobs",
}
_SKIP_FLOW_PARTS = {
    "tests", "test", "__tests__", "testing", "vendor", "node_modules",
    "migrations", "fixtures", "docs", "images", "public", "static", "build",
    "dist", ".venv", "venv",
}
# HTTP decorators that mark a function as a route handler.
_ROUTE_DECORATORS = {"get", "post", "put", "delete", "patch", "route",
                     "head", "options", "view", "dispatch", "handle"}
# Third-party prefixes that mark a file as touching storage / external APIs.
_STORAGE_IMPORTS = {
    "sqlalchemy", "psycopg", "psycopg2", "pymysql", "sqlite3", "redis",
    "pymongo", "motor", "boto3", "aiosqlite", "duckdb", "sqlite", "elasticsearch",
}
_EXTERNAL_IMPORTS = {
    "requests", "httpx", "aiohttp", "urllib", "urllib3", "openai", "anthropic",
    "langchain", "langgraph", "boto3", "google", "grpc", "kafka", "redis",
    "twilio", "stripe", "sendgrid", "firebase", "certifi",
}

MAX_FLOWS = 6
MAX_DEPTH = 8
MAX_NODES_PER_FLOW = 40


@observe(name="repo_data_flows")
def infer_data_flows(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    files_by_rel: dict[str, str] | None = None,
    max_flows: int = MAX_FLOWS,
) -> dict[str, dict[str, Any]]:
    """Return detected execution flows as ``{flow_id: flow}``.

    ``nodes``/``edges`` come from the static code graph.  ``files_by_rel`` maps
    repo-relative path -> source text for Python files; when provided it is used
    to extract route decorators, defined functions and external imports so every
    flow node is backed by real code.
    """
    files_by_rel = files_by_rel or {}
    by_id = {n["id"]: n for n in nodes}

    out_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    in_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in edges:
        if e.get("kind") == "contains":
            continue
        if e["source"] in by_id and e["target"] in by_id:
            out_edges[e["source"]].append(e)
            in_edges[e["target"]].append(e)

    internal_areas = _internal_areas(nodes)
    entries = _detect_entry_points(nodes, files_by_rel, internal_areas)

    flows: dict[str, dict[str, Any]] = {}
    seen_signatures: set[tuple[str, ...]] = set()
    for entry in entries:
        reachable, flow_edges = _trace(entry["id"], out_edges, by_id)
        if len(reachable) < 2:
            continue
        signature = tuple(sorted(reachable))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        if len(flows) >= max_flows:
            break
        flows[entry["id"]] = _build_flow(
            entry, reachable, flow_edges, by_id, out_edges, in_edges,
            files_by_rel, internal_areas,
        )
    return flows


# ---------------------------------------------------------------------------
# Entry-point detection
# ---------------------------------------------------------------------------

def _detect_entry_points(
    nodes: list[dict[str, Any]],
    files_by_rel: dict[str, str] | None,
    internal_areas: set[str],
) -> list[dict[str, Any]]:
    """Return ordered entry-point candidates (route handlers first)."""
    files_by_rel = files_by_rel or {}
    candidates: list[dict[str, Any]] = []
    for n in nodes:
        if n.get("kind") not in {"file", "module"}:
            continue
        path = n.get("path", "")
        if _is_skipped_path(path):
            continue
        text = files_by_rel.get(path, "")
        score = 0
        endpoints: list[tuple[str, str]] = []
        if text:
            endpoints = _route_endpoints(text)
            if endpoints:
                score += 100
        if _looks_like_entry(path):
            score += 20
        if score:
            candidates.append({
                "id": n["id"],
                "path": path,
                "label": n.get("label", path or n["id"]),
                "score": score,
                "endpoints": endpoints,
            })
    candidates.sort(key=lambda c: (-c["score"], c["path"]))
    return candidates


def _route_endpoints(text: str) -> list[tuple[str, str]]:
    """Return ``(HTTP method, path)`` tuples for route decorators in *text*."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                method = _as_route_method(dec.func.attr)
                if method is None:
                    continue
                route = ""
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    route = str(dec.args[0].value)
                elif dec.keywords and isinstance(dec.keywords[0].value, ast.Constant):
                    route = str(dec.keywords[0].value.value)
                out.append((method, route))
            elif isinstance(dec, ast.Attribute):
                method = _as_route_method(dec.attr)
                if method is not None:
                    out.append((method, ""))
    return out


def _as_route_method(attr: str) -> str | None:
    if attr in _ROUTE_DECORATORS:
        return attr.upper()
    return None


def _looks_like_entry(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1] if parts else path
    if name in _ENTRY_BASENAMES:
        return True
    if len(parts) >= 2 and name.startswith("__init__."):
        return True
    if any(part in _ENTRY_DIR_PARTS for part in parts[:-1]):
        return True
    return False


def _is_skipped_path(path: str) -> bool:
    parts = path.split("/")
    return any(part in _SKIP_FLOW_PARTS for part in parts)


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------

def _trace(
    entry_id: str,
    out_edges: dict[str, list[dict[str, Any]]],
    by_id: dict[str, dict[str, Any]],
) -> tuple[set[str], list[dict[str, Any]]]:
    """Return the node set + edges reachable from *entry_id* following calls."""
    reachable: set[str] = {entry_id}
    frontier: deque[tuple[str, int]] = deque([(entry_id, 0)])
    while frontier:
        cur, depth = frontier.popleft()
        if depth >= MAX_DEPTH or len(reachable) >= MAX_NODES_PER_FLOW:
            break
        for e in out_edges.get(cur, ()):
            if e["target"] in reachable:
                continue
            reachable.add(e["target"])
            frontier.append((e["target"], depth + 1))
    flow_edges = [
        e
        for edge_list in out_edges.values()
        for e in edge_list
        if e["source"] in reachable and e["target"] in reachable
    ]
    return reachable, flow_edges


# ---------------------------------------------------------------------------
# Flow construction
# ---------------------------------------------------------------------------

def _build_flow(
    entry: dict[str, Any],
    reachable: set[str],
    flow_edges: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    out_edges: dict[str, list[dict[str, Any]]],
    in_edges: dict[str, list[dict[str, Any]]],
    files_by_rel: dict[str, str],
    internal_areas: set[str],
) -> dict[str, Any]:
    ordered = _order_nodes(entry["id"], reachable, flow_edges, by_id)
    nodes_out: list[dict[str, Any]] = []
    for nid in ordered:
        raw = by_id[nid]
        path = raw.get("path", "")
        resp = _flow_node(nid, raw, path, out_edges, in_edges, by_id,
                          files_by_rel, internal_areas,
                          is_entry=(nid == entry["id"]))
        nodes_out.append(resp)

    edges_out = [
        {
            "source": e["source"],
            "target": e["target"],
            "kind": e.get("kind", "calls"),
            "relationship_source": e.get("relationship_source", "ast"),
            "confidence": e.get("confidence", 1.0),
        }
        for e in flow_edges
        if e["source"] in reachable and e["target"] in reachable
    ]

    incount, outcount = _flow_degrees(edges_out)
    for n in nodes_out:
        n["dependents"] = incount.get(n["id"], 0)
        n["deps"] = outcount.get(n["id"], 0)

    bottlenecks = _bottlenecks(nodes_out)

    method = ""
    route = ""
    if entry.get("endpoints"):
        method, route = entry["endpoints"][0]
    title = _flow_title(entry, method, route)

    return {
        "id": entry["id"],
        "title": title,
        "kind": "route" if entry.get("endpoints") else "pipeline",
        "entry": entry["id"],
        "nodes": nodes_out,
        "edges": edges_out,
        "bottlenecks": bottlenecks,
    }


def _flow_node(
    nid: str,
    raw: dict[str, Any],
    path: str,
    out_edges: dict[str, list[dict[str, Any]]],
    in_edges: dict[str, list[dict[str, Any]]],
    by_id: dict[str, dict[str, Any]],
    files_by_rel: dict[str, str],
    internal_areas: set[str],
    is_entry: bool = False,
) -> dict[str, Any]:
    text = files_by_rel.get(path, "")
    functions = _defined_functions(text) if path.endswith((".py", ".pyi")) else []
    callers = _paths_of(in_edges.get(nid, ()), by_id, pick="source")
    callees = _paths_of(out_edges.get(nid, ()), by_id, pick="target")
    dependencies = _external_deps(text, internal_areas) if path.endswith((".py", ".pyi")) else []
    kind = _classify_kind(path, callees, dependencies, is_entry)
    return {
        "id": nid,
        "label": raw.get("label") or path or nid,
        "kind": kind,
        "path": path,
        "entry": is_entry,
        "functions": functions[:8],
        "callers": callers[:8],
        "callees": callees[:8],
        "dependencies": dependencies[:12],
        "deps": raw.get("deps", 0),
        "dependents": raw.get("dependents", 0),
        "latency_ms": None,
    }


def _paths_of(
    edges: Iterable[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    pick: str = "source",
) -> list[str]:
    paths: list[str] = []
    for e in edges:
        node = by_id.get(e.get(pick))
        if node:
            p = node.get("path") or node.get("label")
            if p:
                paths.append(p)
    return _dedup(paths)


def _dedup(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _classify_kind(path: str, callees: list[str], dependencies: list[str], is_entry: bool) -> str:
    if is_entry:
        return "route" if any(p in path for p in _ENTRY_DIR_PARTS) else "input"
    low = path.lower()
    if any(p in low for p in ("service", "services")):
        return "service"
    if any(p in low for p in ("storage", "storages", "db", "database",
                              "persist", "store", "model", "schema", "repo")):
        return "storage"
    if any(p in low for p in ("llm", "generation", "inference", "embed")):
        return "llm"
    if any(p in low for p in ("orchestr", "pipeline", "core")):
        return "core"
    if any(d in storage_deps(dependencies) for d in _STORAGE_IMPORTS):
        return "storage"
    if any(d in external_deps(dependencies) for d in _EXTERNAL_IMPORTS):
        return "external"
    return "module"


def _external_deps(text: str, internal_areas: set[str]) -> list[str]:
    """Third-party import specifiers (excluding internal modules)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    specs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                specs.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            specs.append(node.module)
    external: list[str] = []
    for spec in specs:
        head = spec.split(".")[0]
        if head in internal_areas:
            continue
        if head in _STORAGE_IMPORTS or head in _EXTERNAL_IMPORTS or head.lower().startswith(("aio", "openai", "lang")):
            external.append(spec)
    return _dedup(external)


def _defined_functions(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            names.append(node.name)
    return _dedup(names)


# ---------------------------------------------------------------------------
# Layout ordering + bottlenecks
# ---------------------------------------------------------------------------

def _order_nodes(
    entry_id: str,
    reachable: set[str],
    flow_edges: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Topological-ish ordering: BFS layers away from the entry point."""
    layers: dict[str, int] = {entry_id: 0}
    frontier: deque[str] = deque([entry_id])
    while frontier:
        cur = frontier.popleft()
        for e in flow_edges:
            if e["source"] == cur and e["target"] not in layers:
                layers[e["target"]] = layers[cur] + 1
                frontier.append(e["target"])
    for nid in reachable:
        layers.setdefault(nid, 999)
    return sorted(reachable, key=lambda nid: (layers[nid], nid))


def _flow_degrees(
    edges_out: list[dict[str, Any]],
) -> tuple[defaultdict[str, int], defaultdict[str, int]]:
    """Flow-local in/out degree (callers/dependents, callees) per node."""
    incount: defaultdict[str, int] = defaultdict(int)
    outcount: defaultdict[str, int] = defaultdict(int)
    for e in edges_out:
        outcount[e["source"]] += 1
        incount[e["target"]] += 1
    return incount, outcount


def _bottlenecks(nodes_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real coupling hotspots inside a flow — never fabricated timings."""
    scored = [
        {
            "id": n["id"], "label": n["label"], "kind": n["kind"],
            "path": n["path"], "functions": n["functions"],
            "callers": n["callers"], "callees": n["callees"],
            "dependencies": n["dependencies"],
            "deps": n["deps"], "dependents": n["dependents"],
            "latency_ms": None,
        }
        for n in nodes_out
        if n["dependents"] > 0
    ]
    scored.sort(key=lambda x: (-x["dependents"], len(x.get("callers", []))))
    return scored[:3]


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _internal_areas(nodes: list[dict[str, Any]]) -> set[str]:
    areas: set[str] = set()
    for n in nodes:
        p = n.get("path", "")
        if not p or "/" not in p:
            continue
        areas.add(p.split("/")[0])
    return areas


def storage_deps(dep: Iterable[str]) -> list[str]:
    return [d for d in dep if d.split(".")[0] in _STORAGE_IMPORTS]


def external_deps(dep: Iterable[str]) -> list[str]:
    return [d for d in dep if d.split(".")[0] in _EXTERNAL_IMPORTS]


def _flow_title(entry: dict[str, Any], method: str, route: str) -> str:
    if method and route:
        return f"{method} {route}"
    if method:
        return f"{method} {entry['path']}"
    name = (entry.get("path") or entry.get("label") or "entry").split("/")[-1]
    return re.sub(r"\.[^.]+$", "", name) or "execution flow"
