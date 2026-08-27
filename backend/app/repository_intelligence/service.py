"""Application service for Repository Intelligence.

Layered:  route -> service -> analyzer -> storage.

The service owns the analysis lifecycle (create run, run in the background or
blocking, incremental short-circuit by commit SHA, persist nodes/edges + a
JSON bundle) and rehydrates the typed view models from the store on read.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from . import dependencies as dep_mod
from .analyzer import AnalysisResult, RepositoryAnalyzer
from .git import GitRepoError, GitRepository
from .impact import compute_change_impact
from .schemas import (
    AnalysisStatus,
    AnalysisSummary,
    DependencyGraph,
    RepositoryAnalysis,
    RepositoryEdge,
    RepositoryNode,
)
from .schemas import (
    Repository as RepositorySchema,
)
from .storage import RepositoryStore

__all__ = ["RepositoryIntelligenceError", "RepositoryIntelligenceService"]

logger = logging.getLogger(__name__)


class RepositoryIntelligenceError(RuntimeError):
    """Raised when repository analysis cannot be completed."""


class RepositoryIntelligenceService:
    def __init__(
        self,
        store: RepositoryStore,
        analyzer: RepositoryAnalyzer,
    ) -> None:
        self._store = store
        self._analyzer = analyzer

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start_analysis(self, repo_url: str, branch: str | None = None, force: bool = False) -> dict[str, Any]:
        """Create a run and schedule it in the background.

        Returns a ``{analysis_id, status}`` payload.  The route maps this to
        ``202 Accepted``.
        """
        try:
            git = GitRepository(repo_url, branch=branch)
            owner, name = git.owner, git.name
        except GitRepoError as exc:
            raise RepositoryIntelligenceError(str(exc)) from exc
        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        await self._store.create_run(
            {
                "id": run_id,
                "owner": owner,
                "name": name,
                "full_name": f"{owner}/{name}",
                "repo_url": repo_url,
                "branch": branch or "main",
                "commit": "",
                "status": "queued",
                "progress": 0,
                "incremental": False,
                "created_at": now.isoformat(),
            }
        )
        asyncio.create_task(self._run(run_id, repo_url, branch, force))
        return {"analysis_id": run_id, "status": await self.get_status(run_id)}

    async def run_analysis(
        self, run_id: str, repo_url: str, branch: str | None = None, force: bool = False
    ) -> dict[str, Any]:
        """Run analysis synchronously (blocking) and persist the result."""
        return await self._run(run_id, repo_url, branch, force)

    async def _run(self, run_id: str, repo_url: str, branch: str | None, force: bool) -> dict[str, Any]:
        git: GitRepository | None = None
        try:
            git = GitRepository(repo_url, branch=branch)
            await self._ensure_run(run_id, git, branch)
            await self._store.update_run(run_id, status="running", progress=5)
            await git.clone()
            commit = await git.head_commit()

            # Incremental short-circuit: identical repo+branch+commit.
            owner, name = git.owner, git.name
            latest = await self._store.get_latest_run(owner, name, exclude_run_id=run_id)
            if (
                not force
                and latest
                and latest.get("commit_sha") == commit
                and latest.get("status") == "complete"
                and latest.get("summary_json")
            ):
                logger.info("repo analysis: reuse cached run %s (commit %s)", latest["id"], commit)
                # Reuse the cached analysis by copying its persisted result into
                # the newly-created run_id, so the new run is fully readable.
                summary = latest.get("summary_json") or "{}"
                await self._store.save_analysis(
                    run_id,
                    await self._store.get_nodes(latest["id"]),
                    await self._store.get_edges(latest["id"]),
                    summary,
                )
                await self._store.update_run(
                    run_id,
                    status="complete",
                    progress=100,
                    commit_sha=commit,
                    finished_at=datetime.now(UTC).isoformat(),
                    incremental=True,
                )
                return {"commit": commit, "incremental": True, "reused_commit": commit, "cached_run_id": latest["id"]}

            result = await self._analyzer.analyze(git, run_id=run_id, progress=self._progress(run_id))
            await self._persist(run_id, result)
            git.close()
            logger.info(
                "repo analysis complete: run=%s nodes=%d edges=%d", run_id, len(result.nodes), len(result.edges)
            )
            return {"commit": commit, "incremental": False}
        except GitRepoError as exc:
            await self._store.update_run(
                run_id, status="failed", error=str(exc), finished_at=datetime.now(UTC).isoformat()
            )
            raise RepositoryIntelligenceError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("repo analysis failed: run=%s", run_id)
            await self._store.update_run(
                run_id, status="failed", error=str(exc), finished_at=datetime.now(UTC).isoformat()
            )
            raise RepositoryIntelligenceError(str(exc)) from exc
        finally:
            if git is not None:
                git.close()

    async def _ensure_run(self, run_id: str, git: GitRepository, branch: str | None) -> None:
        """Create the run row if it does not already exist (defensive)."""
        existing = await self._store.get_run(run_id)
        if existing is not None:
            return
        await self._store.create_run(
            {
                "id": run_id,
                "owner": git.owner,
                "name": git.name,
                "full_name": f"{git.owner}/{git.name}",
                "repo_url": git.repo_url,
                "branch": branch or "main",
                "commit": "",
                "status": "queued",
                "progress": 0,
                "incremental": False,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    async def _persist(self, run_id: str, result: AnalysisResult) -> None:
        bundle = dict(result.bundle)
        await self._store.save_analysis(run_id, result.nodes, result.edges, json.dumps(bundle, separators=(",", ":")))

    def _progress(self, run_id: str):
        async def cb(pct: int, msg: str) -> None:
            await self._store.update_run(run_id, progress=pct)
            logger.info("repo analysis %s: %d%% %s", run_id, pct, msg)

        return cb

    # ------------------------------------------------------------------ #
    # Read access — rehydrate typed view models
    # ------------------------------------------------------------------ #

    async def get_status(self, analysis_id: str) -> AnalysisStatus:
        run = await self._store.get_run(analysis_id)
        if run is None:
            raise RepositoryIntelligenceError(f"Analysis '{analysis_id}' not found")
        return AnalysisStatus(
            id=run["id"],
            repo_url=run["repo_url"],
            owner=run["owner"],
            name=run["name"],
            branch=run["branch"],
            status=run["status"],
            progress=run["progress"],
            commit=run.get("commit_sha") or None,
            error=run.get("error"),
            created_at=datetime.fromisoformat(run["created_at"]),
            finished_at=datetime.fromisoformat(run["finished_at"]) if run.get("finished_at") else None,
        )

    async def get_latest_analysis(self, repo_url: str) -> AnalysisStatus:
        """Resolve the most recent *completed* analysis for a repository URL.

        Called by ``GET /repository/latest`` so the frontend can take the
        ``analysis_id`` it receives from ``POST /github/ingest`` and keep
        navigating to the current run (or re-resolve after a refresh).
        """
        try:
            git = GitRepository(repo_url)
            owner, name = git.owner, git.name
        except GitRepoError as exc:
            raise RepositoryIntelligenceError(str(exc)) from exc
        run = await self._store.get_latest_run(owner, name)
        if run is None:
            raise RepositoryIntelligenceError(
                f"No completed analysis for '{owner}/{name}' — repository not found in analysis store"
            )
        return await self.get_status(run["id"])

    async def reanalyze(self, analysis_id: str) -> dict[str, Any]:
        """Force a fresh analysis based on the stored repo_url/branch.

        Returns the same ``{analysis_id, status}`` payload as
        :meth:`start_analysis` but schedules the new run with ``force=True``
        so the incremental short-circuit is bypassed.
        """
        run = await self._store.get_run(analysis_id)
        if run is None:
            raise RepositoryIntelligenceError(f"Analysis '{analysis_id}' not found")
        new_run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        await self._store.create_run(
            {
                "id": new_run_id,
                "owner": run["owner"],
                "name": run["name"],
                "full_name": run["full_name"],
                "repo_url": run["repo_url"],
                "branch": run["branch"],
                "commit": "",
                "status": "queued",
                "progress": 0,
                "incremental": False,
                "created_at": now.isoformat(),
            }
        )
        asyncio.create_task(self._run(new_run_id, run["repo_url"], run["branch"], force=True))
        return {"analysis_id": new_run_id, "status": await self.get_status(new_run_id)}

    async def get_analysis(self, analysis_id: str, default_impact: bool = True) -> RepositoryAnalysis:
        await self._require_complete(analysis_id)
        nodes = await self._store.get_nodes(analysis_id)
        edges = await self._store.get_edges(analysis_id)
        run = await self._store.get_run(analysis_id)
        bundle = json.loads(run.get("summary_json") or "{}")

        architecture = self._architecture(nodes, edges)
        dependencies = self._dependencies(nodes, edges)
        change_impact = None
        if default_impact and nodes:
            default_path = _default_impact_path(nodes)
            if default_path:
                change_impact = compute_change_impact(nodes, edges, default_path)

        generated_at = datetime.now(UTC)
        summary = AnalysisSummary(
            id=analysis_id,
            commit=run.get("commit_sha"),
            status=run["status"],
            repository=RepositorySchema(**bundle["repository"]),
            generated_at=generated_at,
            sha256=_sha256(nodes, edges),
        )
        return RepositoryAnalysis(
            summary=summary,
            repository=RepositorySchema(**bundle["repository"]),
            health=_schema_health(bundle["health"]) if "health" in bundle else None,
            architecture=architecture,
            dependencies=dependencies,
            data_flows=bundle.get("data_flows", {}),
            git_history=bundle["git_history"],
            ownership=bundle["ownership"],
            change_impact=change_impact,
            risk_explanations=bundle.get("risk_explanations", {}),
            ranked_modules=bundle.get("ranked_modules", []),
            activity=bundle.get("activity", []),
            suggested_questions=bundle.get("suggested_questions", {}).get("questions", []),
        )

    async def get_architecture(self, analysis_id: str) -> DependencyGraph:
        await self._require_complete(analysis_id)
        nodes = await self._store.get_nodes(analysis_id)
        edges = await self._store.get_edges(analysis_id)
        return self._architecture(nodes, edges)

    async def get_dependencies(self, analysis_id: str, selected: str | None, depth: int = 2) -> DependencyGraph:
        await self._require_complete(analysis_id)
        nodes = await self._store.get_nodes(analysis_id)
        edges = await self._store.get_edges(analysis_id)
        center = selected or _default_dependency_center(nodes)
        graph = dep_mod.build_dependency_subgraph(nodes, edges, center, depth)
        return self._graph(graph["nodes"], graph["edges"])

    async def get_change_impact(self, analysis_id: str, path: str) -> dict[str, Any]:
        await self._require_complete(analysis_id)
        nodes = await self._store.get_nodes(analysis_id)
        edges = await self._store.get_edges(analysis_id)
        return compute_change_impact(nodes, edges, path)

    async def get_module_details(self, analysis_id: str, node_id: str) -> dict[str, Any]:
        await self._require_complete(analysis_id)
        nodes = await self._store.get_nodes(analysis_id)
        run = await self._store.get_run(analysis_id)
        node = next((n for n in nodes if n["id"] == node_id), None)
        if node is None:
            raise RepositoryIntelligenceError(f"Node '{node_id}' not found")
        bundle = json.loads(run.get("summary_json") or "{}")
        # recent changes: pull from stored activity, scoped to this node path.
        activity = [a for a in bundle.get("activity", []) if (node.get("path") in a.get("message", ""))][:3]
        top_deps = [
            e["target"]
            for e in (await self._store.get_edges(analysis_id))
            if e["source"] == node_id and e["kind"] in {"imports", "calls"}
        ][:5]
        return {
            "path": node.get("path") or node.get("label"),
            "type": node.get("kind"),
            "files": node.get("files", 0),
            "loc": node.get("loc", 0),
            "deps": node.get("deps", 0),
            "dependents": node.get("dependents", 0),
            "risk": node.get("risk", "Low"),
            "coverage": node.get("coverage", 0.0),
            "changed": _changed_label(node),
            "contributors": [],
            "top_dependencies": top_deps,
            "recent_changes": activity,
        }

    # ------------------------------------------------------------------ #
    # Lightweight bundle sub-views
    # ------------------------------------------------------------------ #

    async def get_data_flows(self, analysis_id: str) -> dict[str, Any]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("data_flows", {})

    async def get_chat_scope(self, analysis_id: str) -> dict[str, Any]:
        """Return the repository URL/branch a completed analysis was run on.

        Used by the ``ask`` endpoint to (re)index the repository into the RAG
        store and scope the question to it.
        """
        await self._require_complete(analysis_id)
        run = await self._store.get_run(analysis_id)
        return {
            "repo_url": run["repo_url"],
            "branch": run.get("branch") or None,
        }

    async def get_git_history(self, analysis_id: str) -> dict[str, Any]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("git_history", {})

    async def get_ownership(self, analysis_id: str) -> dict[str, Any]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("ownership", {})

    async def get_health(self, analysis_id: str) -> dict[str, Any]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("health", {})

    async def get_repository(self, analysis_id: str) -> dict[str, Any]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("repository", {})

    async def get_ranked_modules(self, analysis_id: str) -> list[dict[str, Any]]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("ranked_modules", [])

    async def get_risk_explanations(self, analysis_id: str) -> dict[str, str]:
        bundle = await self._summary_bundle(analysis_id)
        return bundle.get("risk_explanations", {})

    async def _summary_bundle(self, analysis_id: str) -> dict[str, Any]:
        await self._require_complete(analysis_id)
        run = await self._store.get_run(analysis_id)
        return json.loads(run.get("summary_json") or "{}")

    # ------------------------------------------------------------------ #
    # Graph view helpers
    # ------------------------------------------------------------------ #

    def _architecture(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> DependencyGraph:
        return self._graph(nodes, edges)

    def _dependencies(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> DependencyGraph:
        center = _default_dependency_center(nodes)
        graph = dep_mod.build_dependency_subgraph(nodes, edges, center, 2)
        return self._graph(graph["nodes"], graph["edges"])

    def _graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> DependencyGraph:
        return DependencyGraph(
            nodes=[NodeView.to_schema(n) for n in nodes],
            edges=[EdgeView.to_schema(e) for e in edges],
        )

    async def _require_complete(self, analysis_id: str) -> None:
        run = await self._store.get_run(analysis_id)
        if run is None:
            raise RepositoryIntelligenceError(f"Analysis '{analysis_id}' not found")
        if run["status"] != "complete":
            raise RepositoryIntelligenceError(f"Analysis '{analysis_id}' is {run['status']}, not complete")
        if not run.get("summary_json"):
            raise RepositoryIntelligenceError(f"Analysis '{analysis_id}' has no persisted result")


# ---------------------------------------------------------------------------
# View builders (dict -> typed schema)
# ---------------------------------------------------------------------------


class NodeView:
    @staticmethod
    def to_schema(n: dict[str, Any]) -> RepositoryNode:
        meta = dict(n.get("meta") or {})
        meta.setdefault("path", n.get("path", ""))
        meta.setdefault("files", n.get("files", 0))
        meta.setdefault("loc", n.get("loc", 0))
        meta.setdefault("deps", n.get("deps", 0))
        meta.setdefault("dependents", n.get("dependents", 0))
        meta.setdefault("risk", n.get("risk", "Low"))
        meta.setdefault("coverage", n.get("coverage", 0.0))
        meta.setdefault("changed", _changed_label(n))
        return RepositoryNode(
            id=n["id"],
            label=n.get("label", ""),
            kind=n.get("kind", "file"),
            x=n.get("x"),
            y=n.get("y"),
            meta=meta,
        )


class EdgeView:
    @staticmethod
    def to_schema(e: dict[str, Any]) -> RepositoryEdge:
        return RepositoryEdge(
            source=e["source"],
            target=e["target"],
            kind=e.get("kind", "imports"),
            relationship_source=e.get("relationship_source", "ast"),
            confidence=e.get("confidence", 1.0),
        )


def _default_dependency_center(nodes: list[dict[str, Any]]) -> str:
    """Pick a central, high-fan-out node as the default dependency focus."""
    if not nodes:
        return "repo"
    candidates = [n for n in nodes if n.get("kind") == "file"]
    if not candidates:
        return "repo"
    return max(candidates, key=lambda n: n.get("dependents", 0) + n.get("deps", 0))["id"]


def _default_impact_path(nodes: list[dict[str, Any]]) -> str | None:
    center = _default_dependency_center(nodes)
    node = next((n for n in nodes if n["id"] == center), None)
    return node.get("path") if node else None


def _changed_label(n: dict[str, Any]) -> str:
    churn = n.get("_churn", 0) or n.get("signals", {}).get("churn", 0)
    if churn == 0:
        return "stable"
    if churn < 3:
        return "recently"
    return "active"


def _sha256(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for n in sorted(nodes, key=lambda x: x["id"]):
        digest.update(n["id"].encode())
    for e in sorted(edges, key=lambda x: (x["source"], x["target"])):
        digest.update((e["source"] + e["target"]).encode())
    return digest.hexdigest()[:16]


def _schema_health(h: dict[str, Any]) -> Any:
    from .schemas import HealthDimension, RepositoryHealth

    return RepositoryHealth(
        score=h.get("score", 0.0),
        dimensions=[HealthDimension(**d) for d in h.get("dimensions", [])],
    )
