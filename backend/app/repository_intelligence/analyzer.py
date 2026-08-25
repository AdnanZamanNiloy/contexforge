"""Repository Intelligence analysis pipeline.

A single, focused orchestrator (``RepositoryAnalyzer``) drives the whole
analysis.  It is intentionally independent of ``core.orchestrator`` so the
RAG god-object is not coupled to repository analysis.

Sequence:  clone -> graph -> dependencies -> co-ownership -> risk -> git ->
data flows -> health  (each step is traced with ``@observe``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from observability.tracer import observe

from . import dependencies as dep_mod
from .data_flow import infer_data_flows
from .git import GitRepository
from .graph import build_graph
from .risk import (
    RISK_EXPLANATIONS,
    apply_risk_to_nodes,
    compute_repo_health,
    coverage_for_nodes,
    ownership_concentration,
)

__all__ = ["AnalysisResult", "RepositoryAnalyzer"]

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


@dataclass
class AnalysisResult:
    """Result of a completed repository analysis."""

    run_id: str
    owner: str
    name: str
    full_name: str
    repo_url: str
    branch: str
    commit: str
    language: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    bundle: dict[str, Any] = field(default_factory=dict)


class RepositoryAnalyzer:
    """Compute the full Repository Intelligence analysis for a clone."""

    @observe(name="repo_analyze")
    async def analyze(
        self,
        git: GitRepository,
        run_id: str,
        window: str = "all",
        progress: ProgressCallback | None = None,
    ) -> AnalysisResult:
        root = git.workdir
        await self._report(progress, 5, "Resolving repository metadata")

        meta = await git.repository_meta()
        commit = meta["sha"]
        branch = git.branch or "main"

        await self._report(progress, 12, "Scanning source files")
        graph = build_graph(root)
        nodes: list[dict[str, Any]] = graph["nodes"]
        edges: list[dict[str, Any]] = graph["edges"]
        language = graph["language"]
        for n in nodes:
            if n.get("kind") == "repo":
                n["meta"] = {"commit": commit, "author": meta["author"]}

        await self._report(progress, 25, "Reading git history")
        commits = await git.commits(window=window)
        branches = await git.branches()
        churn = await git.file_churn(window=window)
        ownership = await git.ownership(window=window)
        contributors = await git.contributors(window=window)

        churn_by_rel = {c["name"]: c["value"] for c in churn}
        for n in nodes:
            n["_churn"] = churn_by_rel.get(n.get("path"), 0)

        await self._report(progress, 45, "Building dependency graph")
        files_by_rel = _read_sources(root, graph["files"])
        ns_map = _build_namespace_map(nodes)
        call_edges = dep_mod.derive_calls(nodes, edges, ns_map, files_by_rel)
        edges.extend(call_edges)
        nodes = dep_mod.enrich_nodes_with_degree(nodes, edges)

        await self._report(progress, 60, "Attributing ownership")
        files = [n for n in nodes if n.get("kind") == "file"]
        cov = coverage_for_nodes(files)
        for n in nodes:
            if n.get("kind") == "file":
                n["coverage"] = cov.get(n.get("path", ""), 0.0)
        for n in nodes:
            path = n.get("path", "")
            if n.get("kind") != "file":
                n["coverage"] = _aggregate_coverage(nodes, path)
            owners = ownership.get("files", {}).get(path)
            n["ownership_risk"] = ownership_concentration(
                [{"count": c} for a, c in (owners or {}).items()],
                path,
            ) if owners else 0.0

        await self._report(progress, 75, "Scoring risk")
        nodes = apply_risk_to_nodes(nodes, churn_by_rel)
        for n in nodes:
            n.setdefault("signals", {})["churn"] = n.get("_churn", 0)

        await self._report(progress, 85, "Inferring data flows & health")
        repository = self._repository_view(
            git, meta, nodes, language, commits, branches, contributors,
        )
        health = compute_repo_health(nodes)
        data_flows = infer_data_flows(nodes, edges, files_by_rel)
        ranked = dep_mod.ranked_modules(nodes)
        activity = self._activity(commits)
        ownership_view = self._ownership_view(contributors, nodes, ownership, commits)
        git_history = self._git_history(commits, branches, churn, window)
        suggested = self._suggested_questions()

        _assign_layout(nodes, edges)

        bundle = {
            "repository": repository,
            "health": health,
            "data_flows": data_flows,
            "ranked_modules": ranked,
            "activity": activity,
            "ownership": ownership_view,
            "git_history": git_history,
            "suggested_questions": {"questions": suggested},
            "risk_explanations": RISK_EXPLANATIONS,
        }

        await self._report(progress, 95, "Finalising")
        return AnalysisResult(
            run_id=run_id,
            owner=git.owner,
            name=git.name,
            full_name=f"{git.owner}/{git.name}",
            repo_url=git.repo_url,
            branch=branch,
            commit=commit,
            language=language,
            nodes=nodes,
            edges=edges,
            bundle=bundle,
        )

    # ------------------------------------------------------------------ #
    # View builders
    # ------------------------------------------------------------------ #

    def _repository_view(
        self,
        git: GitRepository,
        meta: dict[str, Any],
        nodes: list[dict[str, Any]],
        language: str,
        commits: list[dict[str, Any]],
        branches: list[dict[str, Any]],
        contributors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        file_count = sum(1 for n in nodes if n.get("kind") == "file")
        module_count = sum(1 for n in nodes if n.get("kind") == "module")
        return {
            "owner": git.owner,
            "name": git.name,
            "full_name": f"{git.owner}/{git.name}",
            "description": "",
            "visibility": "public",
            "branch": git.branch or "main",
            "default_branch": git.default_branch,
            "language": language,
            "files": file_count,
            "modules": module_count,
            "commits": len(commits),
            "contributors": len(contributors),
            "branches": len(branches),
            "pull_requests": 0,
            "issues": 0,
            "last_analyzed": datetime.now(timezone.utc).isoformat(),
        }

    def _activity(self, commits: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        rows = []
        for i, c in enumerate(commits[:limit]):
            rows.append({
                "id": f"a{i+1}",
                "hash": c["sha"][:7],
                "message": c["message"],
                "time": c["time"].isoformat(),
                "author": c["author"],
                "kind": "commit",
            })
        return rows

    def _ownership_view(
        self,
        contributors: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        ownership: dict[str, Any],
        commits: list[dict[str, Any]],
    ) -> dict[str, Any]:
        total = sum(c["commits"] for c in contributors) or 1
        palette = ["#7aa2f7", "#67e0c8", "#b6a1ff", "#f0b36e", "#e07b7b", "#8b94a5"]
        cview = []
        for i, c in enumerate(contributors[:6]):
            cview.append({
                "name": c["name"],
                "commits": c["commits"],
                "percent": round(c["commits"] / total * 100, 1),
                "color": palette[i % len(palette)],
            })

        # Module ownership: top module/dir nodes by files.
        files_by_path = ownership.get("files", {})
        mview = []
        for n in sorted(
            (x for x in nodes if x.get("kind") in {"module", "directory"}),
            key=lambda x: x.get("files", 0), reverse=True,
        )[:6]:
            owner_info = _node_owners(n, files_by_path)
            if not owner_info:
                continue
            top = owner_info[0]
            mview.append({
                "name": n.get("path") or n.get("label"),
                "owner": top["name"],
                "percent": round(top["count"] / (sum(o["count"] for o in owner_info) or 1) * 100, 1),
                "files": n.get("files", 0),
                "contributors": [
                    {"name": o["name"],
                     "percent": round(o["count"] / (sum(x["count"] for x in owner_info) or 1) * 100, 1)}
                    for o in owner_info[:3]
                ],
            })

        top1 = cview[0]["percent"] if cview else 0
        top3 = sum(c["percent"] for c in cview[:3])
        bus_factor = len(cview) if cview else 1
        concentration_risk = ("High" if top1 >= 45 else "Medium" if top1 >= 30 else "Low")

        return {
            "contributors": cview,
            "modules": mview,
            "concentration": {
                "top1": top1, "top3": round(top3, 1),
                "bus_factor": bus_factor, "risk": concentration_risk,
            },
        }

    def _git_history(
        self,
        commits: list[dict[str, Any]],
        branches: list[dict[str, Any]],
        churn: list[dict[str, Any]],
        window: str,
    ) -> dict[str, Any]:
        palette = ["#7aa2f7", "#67e0c8", "#b6a1ff", "#e07b7b", "#f0b36e"]
        bview = [
            {"name": b["name"], "commits": b["commits"],
             "color": palette[i % len(palette)], "active": b["active"]}
            for i, b in enumerate(branches[:6])
        ]
        timeline = _bucket_by_week(commits)
        cview = []
        for c in commits[:20]:
            cview.append({
                "hash": c["sha"][:7],
                "message": c["message"],
                "author": c["author"],
                "time": c["time"].isoformat(),
                "files": 0, "inserts": 0, "deletes": 0,
            })
        return {
            "range": window,
            "branches": bview,
            "timeline": timeline,
            "file_churn": churn[:8],
            "commits": cview,
        }

    def _suggested_questions(self) -> list[str]:
        return [
            "How does GitHub ingestion work?",
            "What are the main dependencies?",
            "Which files are most coupled?",
            "Show me the query pipeline",
            "Why is this module high risk?",
        ]

    @staticmethod
    async def _report(cb: ProgressCallback | None, pct: int, msg: str) -> None:
        if cb:
            await cb(pct, msg)
        logger.info("repo_analyze: %d%% %s", pct, msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_sources(root: Path, files: list[Path]) -> dict[str, str]:
    """Return repo-relative path -> file text for Python sources."""
    out: dict[str, str] = {}
    for fp in files:
        if fp.suffix.lower() not in {".py", ".pyi"}:
            continue
        try:
            out[str(fp.relative_to(root))] = fp.read_text(errors="ignore")
        except OSError:
            continue
    return out


def _build_namespace_map(nodes: list[dict[str, Any]]) -> dict[str, str]:
    ns: dict[str, str] = {}
    for n in nodes:
        if n.get("kind") == "file":
            path = n.get("path", "")
            if path.endswith(".py"):
                ns[path[:-3].replace("/", ".")] = n["id"]
                ns.setdefault(path[:-3].rsplit(".", 1)[-1], n["id"])
    return ns


def _aggregate_coverage(nodes: list[dict[str, Any]], path: str) -> float:
    prefix = path + "/"
    children = [n["coverage"] for n in nodes
                if n.get("kind") == "file" and (n.get("path", "") == path
                                                or n.get("path", "").startswith(prefix))]
    return sum(children) / len(children) if children else 0.0


def _node_owners(n: dict[str, Any], files_by_path: dict[str, dict[str, int]]) -> list[dict[str, int]]:
    hint = n.get("path", "")
    counts: dict[str, int] = {}
    for path, owners in files_by_path.items():
        if path == hint or path.startswith(hint + "/"):
            for author, count in owners.items():
                counts[author] = counts.get(author, 0) + count
    return [{"name": a, "count": c}
            for a, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]


def _bucket_by_week(commits: list[dict[str, Any]], buckets: int = 5) -> list[dict[str, Any]]:
    if not commits:
        return []
    ordered = sorted(commits, key=lambda c: c["time"])
    total = len(ordered)
    size = max(1, -(-total // buckets))
    out = []
    for i in range(0, total, size):
        group = ordered[i:i + size]
        out.append({"week": f"W{i // size + 1}", "commits": len(group)})
    return out


def _assign_layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    """Deterministic layered layout: depth -> x, sibling index -> y."""
    from collections import defaultdict, deque

    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.get("kind") == "contains":
            children[e["source"]].append(e["target"])

    depth: dict[str, int] = {"repo": 0}
    levels: dict[int, list[str]] = defaultdict(list)
    levels[0].append("repo")
    queue: deque[tuple[str, int]] = deque([("repo", 0)])
    while queue:
        cur, d = queue.popleft()
        for child in children.get(cur, ()):
            if child not in depth:
                depth[child] = d + 1
                levels[d + 1].append(child)
                queue.append((child, d + 1))

    by_id = {n["id"]: n for n in nodes}
    # Within each depth level, wrap siblings into a bounded grid so a level
    # with many nodes does not produce a single 1000s-of-px-tall column.
    MAX_ROWS = 12
    ROW_H = 90.0
    for nid, d in depth.items():
        if nid not in by_id:
            continue
        level = levels[d]
        sidx = level.index(nid) if nid in level else 0
        col = sidx // MAX_ROWS
        row = sidx % MAX_ROWS
        by_id[nid]["x"] = 70.0 + d * 260.0 + col * 230.0
        by_id[nid]["y"] = 90.0 + row * ROW_H
