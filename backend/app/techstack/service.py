"""Dependency & Tech Stack scanning.

Layered:  route -> service -> FaissStore + TechStackStore.

The scan reads only manifests, lockfiles and file paths, all reconstructed from
chunks the repository was *already* indexed into — every chunk of a GitHub source
carries its real file path in its metadata.  Nothing is cloned, nothing is
fetched, and no dependency is resolved against a registry, so the whole scan is
string work over data already in memory and finishes in milliseconds rather than
seconds.  That is what makes a 60s hard timeout comfortable rather than tight.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from app.techstack.detectors import detect_technologies, language_histogram, summarise
from app.techstack.manifests import is_manifest, parse_manifest
from app.techstack.storage import TechStackStore
from core.storage.faiss_store import FaissStore
from observability.tracer import observe

__all__ = ["TechStackError", "TechStackService"]

logger = logging.getLogger(__name__)

# Bounds.  A report of "the stack" is still useful when the tail is cut, so the
# scan takes a bounded view rather than refusing to run on a large repository.
MAX_FILES = 300
# Manifest text cap.  A lockfile can be enormous (a 4MB package-lock.json is
# normal); only its declared dependencies matter, so the cap bounds work without
# changing the result for any realistic manifest.
MAX_MANIFEST_CHARS = 400_000
MAX_DEPENDENCIES = 400

# Hard ceiling on the scan.  The work is local string processing over already
# loaded chunks, so this only trips if a single manifest is pathological; it
# exists so the endpoint can never hang.
SCAN_TIMEOUT_SECONDS = 30

_SKIP_DIR = re.compile(
    r"(^|/)(node_modules|\.git|dist|build|target|vendor|__pycache__|\.venv|venv|"
    r"site-packages|coverage|\.next|\.nuxt|out|jspm_packages|\.tox|third_party)(/|$)",
    re.IGNORECASE,
)


class TechStackError(RuntimeError):
    """Raised when a tech stack scan cannot be produced."""


class TechStackService:
    """Scans and caches the tech stack of a project's GitHub source."""

    def __init__(self, store: TechStackStore, faiss: FaissStore) -> None:
        self._store = store
        self._faiss = faiss

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="techstack_get")
    async def get(self, project_id: str) -> dict[str, Any] | None:
        """Return the stored scan for a project, or ``None``."""
        return await self._store.latest(project_id)

    @observe(name="techstack_scan")
    async def scan(self, project_id: str, source_id: str, *, refresh: bool = False) -> dict[str, Any]:
        """Return a cached scan, or scan the indexed source."""
        chunks = await self._faiss.get_chunks_by_source_id(source_id)
        if not chunks:
            raise TechStackError("This GitHub source has no indexed files. Re-ingest the repository and try again.")

        paths, repository, owner, repo = self._collect_paths(chunks, source_id)
        if not paths:
            raise TechStackError("This GitHub source has no indexed files to scan.")

        fingerprint = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
        if not refresh:
            cached = await self._store.get(project_id, fingerprint)
            if cached is not None:
                logger.info("techstack: project=%s fingerprint=%s served from cache", project_id, fingerprint[:12])
                return {**cached, "cached": True, "elapsed_ms": 0}

        started = time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                self._run_scan(paths, chunks, repository, owner, repo, fingerprint),
                timeout=SCAN_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:  # pragma: no cover - timing guard
            logger.exception("techstack: scan timed out for project=%s", project_id)
            raise TechStackError("The tech stack scan timed out. Please try again.") from exc

        elapsed = int((time.perf_counter() - started) * 1000)
        saved = await self._store.upsert(project_id, payload, fingerprint)
        logger.info(
            "techstack: project=%s manifests=%d deps=%d langs=%d elapsed=%dms",
            project_id,
            payload["manifest_count"],
            payload["dependency_count"],
            payload["language_count"],
            elapsed,
        )
        return {**saved, "cached": False, "elapsed_ms": elapsed}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _collect_paths(self, chunks: list, source_id: str) -> tuple[list[str], str, str, str]:
        """Indexed file paths for this source, plus its repository identity."""
        paths: list[str] = []
        seen: set[str] = set()
        repository = ""
        owner = repo = ""
        for chunk in chunks:
            meta = dict(chunk.metadata or {})
            path = (meta.get("path") or "").strip()
            if not path or path in seen:
                continue
            seen.add(path)
            paths.append(path)
            if not repository and meta.get("repo"):
                repository = str(meta["repo"])
            if not owner:
                url = str(meta.get("url") or "")
                match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
                if match:
                    owner, repo = match.group(1), match.group(2).replace(".git", "")
        if "/" in repository and not owner:
            owner, _, repo = repository.partition("/")
        if not repository:
            repository = f"{owner}/{repo}" if owner else source_id.replace("repo:", "")
        paths.sort()
        return paths, repository, owner, repo

    async def _run_scan(
        self,
        paths: list[str],
        chunks: list,
        repository: str,
        owner: str,
        repo: str,
        fingerprint: str,
    ) -> dict[str, Any]:
        scanable = [p for p in paths if not _SKIP_DIR.search(p)]
        truncated = len(scanable) > MAX_FILES
        if truncated:
            # Shallow paths first: a manifest lives near the top of a tree.
            scanable = sorted(scanable, key=lambda p: (p.count("/"), p))[:MAX_FILES]
            scanable.sort()

        # Manifests are rare, so this walks the whole list rather than indexing
        # it — one pass over ≤300 paths is cheaper than building a map for the
        # handful of hits.
        manifest_paths = [p for p in scanable if is_manifest(p)]

        by_path: dict[str, list] = {}
        for chunk in chunks:
            meta = dict(chunk.metadata or {})
            path = (meta.get("path") or "").strip()
            if path in manifest_paths:
                by_path.setdefault(path, []).append(chunk)

        results = []
        for path in manifest_paths:
            text = "\n".join((c.text or "") for c in by_path.get(path, []))[:MAX_MANIFEST_CHARS]
            parsed = parse_manifest(path, text)
            if parsed is not None:
                results.append(parsed)

        languages = language_histogram(scanable)
        managers = sorted({r.manager for r in results})
        technologies = detect_technologies(results, managers)

        grouped: dict[str, dict[str, Any]] = {}
        dependency_total = 0
        for result in results:
            bucket = grouped.setdefault(
                result.manager,
                {"manager": result.manager, "language": result.language, "count": 0, "dependencies": []},
            )
            for dep in result.dependencies:
                # A package declared in two manifests of the same ecosystem is
                # listed once; the first manifest wins.
                if any(d["name"] == dep.name for d in bucket["dependencies"]):
                    continue
                bucket["dependencies"].append(
                    {
                        "name": dep.name,
                        "version": dep.version,
                        "scope": dep.scope,
                        "manifest": result.path,
                    }
                )
                dependency_total += 1
            bucket["count"] = len(bucket["dependencies"])

        # Biggest ecosystems first, but keep a stable order for equal sizes.
        manager_rows = sorted(grouped.values(), key=lambda b: (-b["count"], b["manager"]))
        for bucket in manager_rows:
            bucket["dependencies"].sort(key=lambda d: (d["scope"] != "runtime", d["name"].lower()))

        # Cap the reported total so one enormous lockfile cannot dominate the UI.
        truncated_deps = dependency_total > MAX_DEPENDENCIES
        if truncated_deps:
            spent = 0
            for bucket in manager_rows:
                kept = []
                for dep in bucket["dependencies"]:
                    if spent >= MAX_DEPENDENCIES:
                        break
                    kept.append(dep)
                    spent += 1
                bucket["dependencies"] = kept
                bucket["count"] = len(kept)
            dependency_total = sum(b["count"] for b in manager_rows)

        frameworks = [t for t in technologies if t["kind"] in ("Framework", "UI framework")]
        return {
            "repository": repository,
            "summary": summarise(languages, technologies, managers, len(results), dependency_total),
            "languages": languages,
            "frameworks": frameworks,
            "technologies": technologies,
            "package_managers": [
                {"name": m, "dependency_count": next((b["count"] for b in manager_rows if b["manager"] == m), 0)}
                for m in managers
            ],
            "dependencies": manager_rows,
            "manifests": [
                {
                    "path": r.path,
                    "manager": r.manager,
                    "language": r.language,
                    "dependency_count": len(r.dependencies),
                    "error": r.error,
                }
                for r in sorted(results, key=lambda r: r.path)
            ],
            "skipped": max(0, len(paths) - len(scanable)),
            "manifest_count": len(results),
            "dependency_count": dependency_total,
            "language_count": len([row for row in languages if row["kind"] == "programming"]),
            "fingerprint": fingerprint,
            "truncated": truncated or truncated_deps,
        }
