"""Health Score & Hotspots scanning.

Layered:  route -> service -> FaissStore + HealthStore.

The scan reads function source out of chunks the repository was *already*
indexed into.  For Python, the code chunker stores one chunk per function,
method and class — the exact source segment, tagged with the symbol name — so
the metrics can be computed straight from the index with no re-parsing of files
and no clone.  Everything is integer arithmetic over a fixed formula, so a cold
scan finishes in milliseconds.

Two limits are reported rather than papered over:

* **Change frequency is not available.**  The defining idea behind the tool this
  is ported from is that a hotspot is code which is *complex and changes often*,
  and only the first half is measurable here: no git history is indexed, so a
  churn signal would have to be invented.  It is left out and said out loud.
* **Only Python is measured per function.**  Every other language is indexed
  with whole-file chunks, so there is no per-function text to measure.  Those
  files are still reported, by size, which is a fact rather than an estimate.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from app.health.fetch import GitFileFetcher
from app.health.metrics import iter_symbols
from app.health.risk import BANDS, RISK_WEIGHTS, analyze, health_from_bands
from app.health.storage import HealthStore
from core.storage.faiss_store import FaissStore
from observability.tracer import observe

__all__ = ["HealthError", "HealthService"]

logger = logging.getLogger(__name__)

# Bounds. A health report is about the risky tail, so ranking can stop early
# without changing the answer.
MAX_SYMBOLS = 4000
MAX_HOTSPOTS = 15
MAX_FILES = 15
MAX_LARGEST = 12
MAX_SOURCE_CHARS = 200_000

# Hard ceiling. The work is AST parsing of already-loaded chunks, so this only
# trips on a pathological file; it exists so the endpoint can never hang.
SCAN_TIMEOUT_SECONDS = 30

_SKIP_DIR = re.compile(
    r"(^|/)(node_modules|\.git|dist|build|target|vendor|__pycache__|\.venv|venv|"
    r"site-packages|coverage|\.next|\.nuxt|out|\.tox|migrations)(/|$)",
    re.IGNORECASE,
)
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)(test_[^/]*|[^/]*_test)\.[a-z]+$", re.IGNORECASE)

# Languages with a per-function chunk. Extending this means teaching the
# scan another parser; the response says which languages were actually measured
# so the report never implies broader coverage than it has.
_MEASURED_SUFFIX = ".py"


class HealthError(RuntimeError):
    """Raised when a health scan cannot be produced."""


class HealthService:
    """Measures deterministic structural risk across a project's GitHub source."""

    def __init__(self, store: HealthStore, faiss: FaissStore) -> None:
        self._store = store
        self._faiss = faiss

    @observe(name="health_get")
    async def get(self, project_id: str, source_id: str = "") -> dict[str, Any] | None:
        return await self._store.latest(project_id, source_id or "")

    @observe(name="health_scan")
    async def scan(self, project_id: str, source_id: str, *, refresh: bool = False) -> dict[str, Any]:
        chunks = await self._faiss.get_chunks_by_source_id(source_id)
        if not chunks:
            raise HealthError("This GitHub source has no indexed files. Re-ingest the repository and try again.")

        paths, repository, owner, repo = self._collect_paths(chunks, source_id)
        if not paths:
            raise HealthError("This GitHub source has no indexed files to scan.")

        fingerprint = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
        if not refresh:
            cached = await self._store.get(project_id, source_id or "", fingerprint)
            if cached is not None:
                logger.info("health: project=%s fingerprint=%s served from cache", project_id, fingerprint[:12])
                return {**cached, "cached": True, "elapsed_ms": 0}

        started = time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                self._run_scan(chunks, repository, owner, repo, fingerprint),
                timeout=SCAN_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:  # pragma: no cover - timing guard
            logger.exception("health: scan timed out for project=%s", project_id)
            raise HealthError("The health scan timed out. Please try again.") from exc

        elapsed = int((time.perf_counter() - started) * 1000)
        payload["source_id"] = source_id or ""
        saved = await self._store.upsert(project_id, source_id or "", payload, fingerprint)
        logger.info(
            "health: project=%s symbols=%d files=%d health=%d elapsed=%dms",
            project_id,
            payload["symbol_count"],
            payload["file_count"],
            payload["health"],
            elapsed,
        )
        return {**saved, "cached": False, "elapsed_ms": elapsed}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _collect_paths(self, chunks: list, source_id: str) -> tuple[list[str], str, str, str]:
        """Indexed file paths, plus the repository's ``owner`` and ``repo``."""
        paths: set[str] = set()
        repository = ""
        owner = repo = ""
        for chunk in chunks:
            meta = dict(chunk.metadata or {})
            path = (meta.get("path") or "").strip()
            if path:
                paths.add(path)
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
        return sorted(paths), repository, owner, repo

    @staticmethod
    def _rows_for(symbols) -> list[dict[str, Any]]:
        """Turn measured symbols into report rows, with the LRS workings kept.

        The transformed components travel with each row so a reader can
        reproduce the score from the raw metrics without rerunning anything.
        """
        rows: list[dict[str, Any]] = []
        for metrics in symbols:
            components, lrs, band = analyze(metrics)
            rows.append(
                {
                    "name": metrics.name,
                    "kind": metrics.kind,
                    "path": metrics.path,
                    "loc": metrics.loc,
                    "cc": metrics.cc,
                    "nd": metrics.nd,
                    "fo": metrics.fo,
                    "ns": metrics.ns,
                    "r_cc": round(components.r_cc, 2),
                    "r_nd": round(components.r_nd, 2),
                    "r_fo": round(components.r_fo, 2),
                    "r_ns": round(components.r_ns, 2),
                    "lrs": round(lrs, 2),
                    "band": band.name,
                    "band_label": band.label,
                    "test": bool(_TEST_PATH.search(metrics.path)),
                }
            )
        return rows

    async def _run_scan(
        self,
        chunks: list,
        repository: str,
        owner: str,
        repo: str,
        fingerprint: str,
    ) -> dict[str, Any]:
        # Group the source's chunks by file, keeping them in index order.
        by_path: dict[str, list] = {}
        for chunk in chunks:
            meta = dict(chunk.metadata or {})
            path = (meta.get("path") or "").strip()
            if not path or _SKIP_DIR.search(path):
                continue
            by_path.setdefault(path, []).append(chunk)

        rows: list[dict[str, Any]] = []
        measured_paths = 0
        unparseable_paths = 0
        unresolved: list[str] = []

        # Pass one: everything the index can supply on its own.  A repository
        # indexed with the code chunker stores one chunk per function tagged
        # with its symbol, which is the exact source.  Older indexes hold the
        # file split on text-chunk boundaries, which reassembles only when the
        # joins land somewhere syntactically whole.
        for path, file_chunks in by_path.items():
            if not path.endswith(_MEASURED_SUFFIX):
                continue
            if not any((c.text or "").strip() for c in file_chunks):
                continue

            symbol_chunks = [c for c in file_chunks if str((c.metadata or {}).get("symbol") or "").strip()]
            if symbol_chunks:
                source = "\n\n".join(c.text or "" for c in symbol_chunks)[:MAX_SOURCE_CHARS]
            else:
                source = "\n\n".join(c.text or "" for c in file_chunks)[:MAX_SOURCE_CHARS]

            symbols = iter_symbols(source, path)
            if symbols is None:
                unresolved.append(path)
                continue
            measured_paths += 1
            rows.extend(self._rows_for(symbols))

        # Pass two: fetch the rest.  A text-split index often cuts a file mid
        # class, and the missing text is simply not in the index, so the only way
        # to measure it exactly is to read the file.  Bounded to the files that
        # actually need it, and skipped entirely when everything resolved.
        fetched = 0
        unreachable = False
        if unresolved and owner and repo:
            # The fetcher finds the branch itself, preferring candidates that need
            # no API quota: being rate-limited on the branch lookup used to
            # disable this phase entirely, and the report just came back empty.
            fetcher = GitFileFetcher(owner, repo)
            outcome = await fetcher.fetch(unresolved)
            unreachable = fetcher.branch_unresolved
            for path in unresolved:
                text = outcome.files.get(path)
                if not text:
                    continue
                symbols = iter_symbols(text[:MAX_SOURCE_CHARS], path)
                if symbols is None:
                    continue
                fetched += 1
                measured_paths += 1
                rows.extend(self._rows_for(symbols))
        unparseable_paths = len(unresolved) - fetched

        if len(rows) >= MAX_SYMBOLS:
            rows = rows[:MAX_SYMBOLS]

        counts = {band.name: 0 for band in BANDS}
        for row in rows:
            counts[row["band"]] = counts.get(row["band"], 0) + 1

        ranked = sorted(rows, key=lambda r: (-r["lrs"], r["path"], r["name"]))
        hotspots = [r for r in ranked if not r["test"]][:MAX_HOTSPOTS]

        # One row per file: the worst symbol in it, which is what "a hotspot in
        # this file" means to a reader.
        worst_by_file: dict[str, dict[str, Any]] = {}
        file_symbols: dict[str, int] = {}
        file_loc: dict[str, int] = {}
        for row in rows:
            path = row["path"]
            file_symbols[path] = file_symbols.get(path, 0) + 1
            file_loc[path] = file_loc.get(path, 0) + row["loc"]
            current = worst_by_file.get(path)
            if current is None or row["lrs"] > current["lrs"]:
                worst_by_file[path] = row
        files = sorted(worst_by_file.values(), key=lambda r: (-r["lrs"], r["path"]))[:MAX_FILES]

        # Every indexed file, not just Python, so a non-Python repository still
        # says something true about its size.
        all_paths = {path: sum(len(c.text or "") for c in file_chunks) for path, file_chunks in by_path.items()}
        largest = sorted(
            (
                {"path": path, "chars": size, "measured": path.endswith(_MEASURED_SUFFIX)}
                for path, size in all_paths.items()
            ),
            key=lambda r: -r["chars"],
        )[:MAX_LARGEST]

        # With no symbols there is no health to report: `None` is not the same as 100.
        health = health_from_bands(counts, len(rows)) if rows else None
        measured = ["Python"] if rows else []
        return {
            "repository": repository,
            "health": health,
            "band": _overall_band(rows).name,
            "summary": _summary(health, counts, len(rows), len(all_paths), measured),
            "weights": dict(RISK_WEIGHTS),
            "band_counts": counts,
            "hotspots": hotspots,
            "files": files,
            "largest_files": largest,
            "symbol_count": len(rows),
            "file_count": len(all_paths),
            "measured_languages": measured,
            "measured_files": measured_paths,
            "unparsed_files": unparseable_paths,
            "fetched_files": fetched,
            "coverage_note": _coverage_note(measured, len(all_paths), unparseable_paths, fetched, unreachable),
            "fingerprint": fingerprint,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# --------------------------------------------------------------------------- #


def _overall_band(rows: list[dict[str, Any]]) -> Any:
    """The band of the worst symbol, or low when there is nothing measured.

    A repository's headline band follows its worst code rather than its average,
    because a single critical function is the thing a reader needs to see.
    """
    from app.health.risk import band_for

    if not rows:
        return band_for(0.0)
    return band_for(max(r["lrs"] for r in rows))


def _summary(health: int, counts: dict[str, int], symbols: int, files: int, measured: list[str]) -> str:
    if not symbols:
        return (
            f"No per-function risk could be measured across {files} indexed file"
            f"{'' if files == 1 else 's'}. Structural risk is measured for Python sources."
        )
    notable = [f"{counts.get(band, 0)} {band}" for band in ("critical", "high") if counts.get(band)]
    detail = f", including {', '.join(notable)}" if notable else ""
    return (
        f"Health {health}/100 across {symbols} function"
        f"{'' if symbols == 1 else 's'} in {files} indexed file{'' if files == 1 else 's'}{detail}."
    )


def _count(value: int, noun: str) -> str:
    """``1 file`` / ``2 files`` — used where the verb has to agree with it."""
    return f"{value} {noun}" if value == 1 else f"{value} {noun}s"


def _coverage_note(measured: list[str], files: int, unparsed: int, fetched: int = 0, unreachable: bool = False) -> str:
    scope = f"for {', '.join(measured)} only" if measured else "for Python only"
    note = (
        f"Per-function risk is measured {scope}; other files are listed by size. "
        f"Change frequency is not available, because no git history is indexed, so churn is "
        f"deliberately left out rather than estimated."
    )
    if fetched:
        note += (
            f" {_count(fetched, 'file')} had to be read from GitHub, because the index stores "
            f"them cut at chunk boundaries."
        )
    if unparsed:
        if unreachable:
            # The cause matters: a rate limit is temporary and the files are fine.
            note += (
                f" {_count(unparsed, 'file')} could not be read from GitHub because the branch lookup"
                f" is rate-limited, so a GITHUB_TOKEN would let this scan measure them."
            )
        else:
            # "1 file ... was" and "2 files ... were" both have to read correctly.
            verb = "was" if unparsed == 1 else "were"
            note += f" {_count(unparsed, 'file')} could not be read and {verb} skipped."
    return note
