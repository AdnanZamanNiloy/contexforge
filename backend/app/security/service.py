"""The Security & Quality scan.

Three sources of evidence, kept distinct because they carry different weight and
a report that blurs them is not worth reading:

* **code** -- structural patterns matched by ast-grep, plus credential shapes.
  Precise: a password in a comment is not a finding, a real ``eval`` is.
* **dependency** -- published advisories for the versions actually declared.
  This is the axis semgrep does not have, and usually the most actionable.
* **quality** -- repository gates that are not vulnerabilities at all: no CI, no
  lockfile, no licence, floating version pins.  Reported as observations rather
  than as findings, because "this repository has no tests" is a fact, not a
  defect someone introduced.

What this deliberately does **not** do is track data across files.  Semgrep's
taint mode follows a value from an untrusted source to a dangerous sink across
function and file boundaries, and nothing here attempts that.  A call to a
helper that ends in ``eval`` is invisible to a per-file pattern match.  The
report says so rather than implying a clean bill of health, because a scanner
that does not mention its blind spot gets trusted for the things it cannot see.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from app.security.code import MAX_FINDINGS, scan_code
from app.security.cves import check_dependencies
from app.security.models import CODE_CATEGORIES, Finding, severity_rank, worst
from app.security.storage import SecurityStore
from app.techstack.manifests import is_manifest, parse_manifest
from core.storage.faiss_store import FaissStore
from observability.tracer import observe

__all__ = ["SecurityError", "SecurityService"]

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 120
#: Bounds mirroring the tech stack scan, so the two views agree on how much of a
#: large repository they looked at.
MAX_FILES = 400
MAX_FILE_CHARS = 120_000
#: A lockfile can be enormous; only its declared dependencies matter.
MAX_MANIFEST_CHARS = 400_000

_SKIP_DIR = re.compile(
    r"(^|/)(node_modules|\.git|dist|build|target|vendor|__pycache__|\.venv|venv|"
    r"site-packages|coverage|\.next|\.nuxt|out|bower_components|jspm_packages|\.tox|"
    r"\.mypy_cache|\.pytest_cache|\.gradle|\.terraform|third_party|thirdparty)(/|$)",
    re.IGNORECASE,
)

#: Extensions worth reading for code patterns.  Deliberately excludes markup,
#: stylesheets and data, where a "pattern" would be noise.
_SOURCE_SUFFIXES = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".rs",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hpp",
    ".hh",
)

_CI_PATHS = (
    ".github/workflows/",
    ".gitlab-ci.yml",
    ".circleci/",
    "Jenkinsfile",
    "azure-pipelines.yml",
    ".travis.yml",
    ".drone.yml",
    "bitbucket-pipelines.yml",
    ".woodpecker.yml",
)
_LOCKFILES = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
    "packages.lock.json",
    "gradle.lockfile",
)
_LICENCE_NAMES = ("LICENSE", "LICENCE", "LICENSE.md", "LICENCE.md", "COPYING", "LICENSE.txt")
_TEST_MARKERS = ("test", "tests", "spec", "__tests__", "testing")
#: A version nobody should ship: floating, or a moving tag.
_FLOATING = re.compile(r"^(?:latest|master|main|next|stable|\*|x|\d+)$", re.IGNORECASE)


class SecurityError(RuntimeError):
    """Raised when a security scan cannot be produced."""


class SecurityService:
    """Scans and caches the security and quality posture of a project's source."""

    def __init__(self, store: SecurityStore, faiss: FaissStore) -> None:
        self._store = store
        self._faiss = faiss
        #: Advisory records keyed by package, held for the life of the process.
        #: An advisory database does not change between two scans of the same
        #: lockfile, so a repeat scan does not re-ask OSV about anything.
        self._advisory_cache: dict[tuple[str, str, str], list[dict]] = {}

    @observe(name="security_get")
    async def get(self, project_id: str, source_id: str = "") -> dict[str, Any] | None:
        return await self._store.latest(project_id, source_id or "")

    @observe(name="security_scan")
    async def scan(self, project_id: str, source_id: str, *, refresh: bool = False) -> dict[str, Any]:
        chunks = await self._faiss.get_chunks_by_source_id(source_id)
        if not chunks:
            raise SecurityError("This GitHub source has no indexed files. Re-ingest the repository and try again.")

        paths, repository, _owner, _repo = self._collect_paths(chunks, source_id)
        if not paths:
            raise SecurityError("This GitHub source has no indexed files to scan.")

        fingerprint = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
        if not refresh:
            cached = await self._store.get(project_id, source_id or "", fingerprint)
            if cached is not None:
                logger.info("security: project=%s fingerprint=%s served from cache", project_id, fingerprint[:12])
                return {**cached, "cached": True, "elapsed_ms": 0}

        started = time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                self._run_scan(chunks, paths, repository, fingerprint), timeout=SCAN_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:  # pragma: no cover - timing guard
            logger.exception("security: scan timed out for project=%s", project_id)
            raise SecurityError("The security scan timed out. Please try again.") from exc

        elapsed = int((time.perf_counter() - started) * 1000)
        payload["source_id"] = source_id or ""
        saved = await self._store.upsert(project_id, source_id or "", payload, fingerprint)
        logger.info(
            "security: project=%s findings=%d deps_vuln=%d gates=%d elapsed=%dms",
            project_id,
            payload["finding_count"],
            payload["dependencies"]["vulnerable"],
            payload["gate_count"],
            elapsed,
        )
        return {**saved, "cached": False, "elapsed_ms": elapsed}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _collect_paths(self, chunks: list, source_id: str) -> tuple[list[str], str, str, str]:
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

    def _reassemble(self, chunks: list, wanted: set[str]) -> dict[str, str]:
        """Rebuild file contents from index chunks.

        The same reasoning the health scan uses: a repository indexed with the
        code chunker stores one chunk per function tagged with its symbol, which
        joined is the file.  An index that split on text boundaries still yields
        usable text, just not guaranteed to be whole -- so the report states how
        many files it read rather than implying it read everything.
        """
        by_path: dict[str, list] = {}
        for chunk in chunks:
            path = (str((chunk.metadata or {}).get("path") or "")).strip()
            if path in wanted:
                by_path.setdefault(path, []).append(chunk)

        files: dict[str, str] = {}
        for path, file_chunks in by_path.items():
            symbol_chunks = [c for c in file_chunks if str((c.metadata or {}).get("symbol") or "").strip()]
            ordered = symbol_chunks or file_chunks
            text = "\n\n".join(c.text or "" for c in ordered)[:MAX_FILE_CHARS]
            if text.strip():
                files[path] = text
        return files

    async def _run_scan(self, chunks: list, paths: list[str], repository: str, fingerprint: str) -> dict[str, Any]:
        scannable = [p for p in paths if not _SKIP_DIR.search(p) and p.lower().endswith(_SOURCE_SUFFIXES)]
        truncated = len(scannable) > MAX_FILES
        if truncated:
            # Shallow first: application code sits near the top of a tree, and a
            # deep fixture directory is the least useful thing to read.
            scannable = sorted(scannable, key=lambda p: (p.count("/"), p))[:MAX_FILES]
            scannable.sort()

        files = self._reassemble(chunks, set(scannable))
        code, advisories = await asyncio.gather(
            scan_code(files),
            self._check_dependencies(chunks, paths),
        )

        findings: list[Finding] = list(code.findings)
        findings.extend(advisories.findings)
        return self._payload(
            paths=paths,
            scannable=scannable,
            files=files,
            code=code,
            advisories=advisories,
            findings=findings,
            repository=repository,
            fingerprint=fingerprint,
            truncated=truncated,
        )

    async def _check_dependencies(self, chunks: list, paths: list[str]):
        """Ask OSV about the versions this repository actually declares.

        The manifests are re-read here rather than read back from the tech stack
        scan: it is a few milliseconds of string work over data already in
        memory, and it means the security view never depends on another view
        having been opened first.
        """
        by_path: dict[str, list] = {}
        for chunk in chunks:
            path = (str((chunk.metadata or {}).get("path") or "")).strip()
            if path and not _SKIP_DIR.search(path) and is_manifest(path):
                by_path.setdefault(path, []).append(chunk)

        results = []
        for path, file_chunks in by_path.items():
            text = "\n".join(c.text or "" for c in file_chunks)[:MAX_MANIFEST_CHARS]
            parsed = parse_manifest(path, text)
            if parsed is not None:
                results.append(parsed)

        rows: list[dict] = []
        for result in results:
            for dep in result.dependencies:
                rows.append({"name": dep.name, "version": dep.version, "manager": result.manager, "scope": dep.scope})
        return await check_dependencies(rows, self._advisory_cache)

    def _payload(
        self,
        *,
        paths: list[str],
        scannable: list[str],
        files: dict[str, str],
        code,
        advisories,
        findings: list[Finding],
        repository: str,
        fingerprint: str,
        truncated: bool,
    ) -> dict[str, Any]:
        findings = _cap(findings)
        code_findings = [f for f in findings if f.source in ("code", "secret")]
        dependency_findings = [f for f in findings if f.source == "dependency"]
        gates = quality_gates(paths, scannable)

        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1

        limit = _stated_limit(code, advisories, files, scannable)
        return {
            "repository": repository,
            "summary": _summary(findings, counts, advisories, code),
            "findings": [f.to_dict() for f in findings],
            "finding_count": len(findings),
            "counts": counts,
            "worst_severity": worst(counts),
            "by_category": _by_category(findings),
            "code": {
                "engine": code.engine,
                "files_scanned": code.files_scanned,
                "files_available": code.files_available,
                "languages": code.languages,
                "finding_count": len(code_findings),
            },
            "dependencies": {
                "checked": advisories.checked,
                "vulnerable": advisories.vulnerable,
                "unchecked": advisories.unchecked,
                "finding_count": len(dependency_findings),
            },
            "quality": gates,
            "gate_count": len(gates),
            "limitations": limit,
            "truncated": truncated or code.files_scanned < code.files_available,
            "fingerprint": fingerprint,
        }


def _cap(findings: list[Finding]) -> list[Finding]:
    """Worst first, most frequent first within a severity, then capped."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.id] = counts.get(finding.id, 0) + 1
    ordered = sorted(
        findings,
        key=lambda f: (
            severity_rank(f.severity),
            0 if f.confidence == "high" else 1,
            -counts[f.id],
            f.location,
            f.line or 0,
        ),
    )
    return ordered[:MAX_FINDINGS]


def _by_category(findings: list[Finding]) -> list[dict]:
    """Findings grouped by category, in the order a reader should meet them."""
    buckets: dict[str, list[Finding]] = {}
    for finding in findings:
        buckets.setdefault(finding.category, []).append(finding)
    order = [*CODE_CATEGORIES, "Vulnerable dependency"]
    rows = [
        {
            "category": category,
            "count": len(buckets[category]),
            "worst_severity": worst(f.severity for f in buckets[category]),
        }
        for category in order
        if category in buckets
    ]
    rows.sort(key=lambda row: (severity_rank(row["worst_severity"]), row["category"]))
    return rows


def _stated_limit(code, advisories, files: dict[str, str], scannable: list[str]) -> list[str]:
    """What this scan did not do.

    Stated plainly in the report.  A scanner that lists its blind spots is one
    whose *findings* can be trusted; one that implies total coverage gets trusted
    for the things it cannot see, which is how a clean report becomes a false
    all-clear.
    """
    limits = [
        "Patterns are matched within a single file. A value that reaches a "
        "dangerous function through a helper in another file is not traced, so "
        "this is not a substitute for taint analysis."
    ]
    if code.engine == "unavailable":
        limits.insert(0, "Code patterns were not checked at all: ast-grep is not installed.")
    elif code.error:
        limits.insert(0, code.error)
    if advisories.error:
        limits.append(f"Dependency advisories are incomplete: {advisories.error}.")
    if advisories.unchecked:
        limits.append(
            f"{advisories.unchecked} declared dependencies were not checked, because they "
            "declare no resolvable version or belong to an ecosystem with no advisory data."
        )
    missing = code.files_available - code.files_scanned
    if missing > 0:
        limits.append(f"{missing} source files were not read, so findings inside them are absent.")
    elif files and not scannable:
        limits.append("No recognised source files were found.")
    return limits


def _summary(findings: list[Finding], counts: dict[str, int], advisories, code) -> str:
    """One or two sentences a reader can act on."""
    if not findings:
        if code.engine == "unavailable":
            return (
                "No issues were found, but code patterns were not checked because ast-grep "
                "is not installed. Only credential shapes were scanned."
            )
        if advisories.checked:
            return (
                f"Nothing flagged across {code.files_scanned} scanned files and "
                f"{advisories.checked} checked dependencies."
            )
        return f"Nothing flagged across {code.files_scanned} scanned files."

    parts: list[str] = []
    critical = counts.get("critical", 0)
    high = counts.get("high", 0)
    if critical:
        parts.append(f"{critical} critical")
    if high:
        parts.append(f"{high} high")
    if not parts:
        parts.append(f"{len(findings)} lower-severity")

    severities = " and ".join(parts)
    headline = f"{severities} issue{'s' if len(findings) != 1 else ''} found"
    if advisories.vulnerable:
        noun = "dependency" if advisories.vulnerable == 1 else "dependencies"
        headline += f", including {advisories.vulnerable} {noun} with published advisories"
    return f"{headline} across {code.files_scanned} scanned files."


def quality_gates(paths: list[str], scannable: list[str]) -> list[dict]:
    """Repository gates: facts about the project, not defects in the code.

    Each is a statement that can be checked from the file list alone, which is
    why they cost nothing and why none of them is presented as a vulnerability.
    """
    gates: list[dict] = []

    def add(gate_id: str, title: str, state: str, detail: str) -> None:
        gates.append({"id": gate_id, "title": title, "state": state, "detail": detail})

    has_ci = any(any(marker in path for marker in _CI_PATHS) for path in paths)
    add(
        "ci",
        "Continuous integration",
        "ok" if has_ci else "warn",
        "A CI workflow is committed." if has_ci else "No CI workflow was found in this repository.",
    )

    has_lock = any(path.rsplit("/", 1)[-1] in _LOCKFILES for path in paths)
    add(
        "lockfile",
        "Dependency lockfile",
        "ok" if has_lock else "warn",
        "A lockfile pins the versions that will be installed."
        if has_lock
        else "No lockfile: installs are not reproducible.",
    )

    licence_names = {name.upper() for name in _LICENCE_NAMES}
    licence = next((p for p in paths if p.rsplit("/", 1)[-1].upper() in licence_names), None)
    add(
        "licence",
        "Licence file",
        "ok" if licence else "info",
        f"{licence.rsplit('/', 1)[-1]} is present." if licence else "No licence file, so reuse terms are unstated.",
    )

    has_tests = any(any(f"/{marker}/" in f"/{path}" for marker in _TEST_MARKERS) for path in scannable)
    add(
        "tests",
        "Test suite",
        "ok" if has_tests else "info",
        "Test files are present." if has_tests else "No test directory was found among the indexed source.",
    )
    return gates
