"""Bounded GitHub source fetcher for the Health scan.

The index does not always hold whole files.  A repository ingested before the
code chunker was used for GitHub sources has its files stored as text-split
chunks, and those are frequently cut mid-class or mid-string, so they cannot be
reassembled into parseable source — the information is simply not there.

When that happens the file is fetched from GitHub instead, which is what the
ingest path already does and what makes the measurement exact rather than
approximate.  It is deliberately small:

* only files that are already known to be Python sources are fetched, never a
  walk of the tree;
* a hard cap on how many, and on the whole fetch phase;
* a handful of concurrent requests, so a weak machine is not asked to open
  fifty sockets;
* raw.githubusercontent.com, which is a CDN of the file bytes — no API quota is
  spent and no tree walk is repeated;
* if the fetch fails, the scan falls back to whatever the index could provide
  and says so, rather than failing the whole report.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

__all__ = ["FetchOutcome", "GitFileFetcher", "default_branch"]

logger = logging.getLogger(__name__)

# Guard against a path that has been tampered with in the index being turned
# into a request for something other than a file in the repository.
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._\-/]+$")
# Python and markdown source, so the report can read the latter as prose.
_RAIL_SUFFIXES = (".md", ".rst", ".txt")


async def default_branch(owner: str, repo: str, timeout: float = 10.0) -> str | None:
    """Resolve a repository's default branch, or ``None`` if unreachable.

    One API call per scan, cached by the caller for the scan's duration.  The
    index does not record which branch was ingested, so raw file URLs need it.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "ContextForge-HealthScan"},
        ) as client:
            response = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
            if response.status_code != 200:
                return None
            branch = (response.json() or {}).get("default_branch")
            return str(branch) if branch else None
    except Exception as exc:
        logger.debug("health: could not resolve default branch for %s/%s (%s)", owner, repo, exc)
        return None


class FetchOutcome:
    """What the fetch phase managed to retrieve.

    ``files`` maps path -> source text.  ``attempted`` and ``failed`` let the
    report distinguish "this repository has no large files" from "we could not
    reach GitHub", which read very differently to a user.
    """

    __slots__ = ("attempted", "failed", "files", "skipped")

    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.attempted = 0
        self.failed = 0
        self.skipped = 0


class GitFileFetcher:
    """Fetches a bounded set of repository files from raw.githubusercontent.com."""

    def __init__(
        self,
        owner: str,
        repo: str,
        branch: str,
        *,
        max_files: int = 40,
        max_bytes: int = 120_000,
        concurrency: int = 4,
        timeout: float = 12.0,
    ) -> None:
        self._owner = owner
        self._repo = repo
        self._branch = branch
        self._max_files = max_files
        self._max_bytes = max_bytes
        self._concurrency = concurrency
        self._timeout = timeout

    def _url(self, path: str) -> str | None:
        if not _SAFE_PATH.match(path) or ".." in path:
            return None
        # raw.githubusercontent.com serves the file bytes directly and spends no
        # API quota, unlike the contents API.
        return f"https://raw.githubusercontent.com/{self._owner}/{self._repo}/{self._branch}/{path}"

    async def fetch(self, paths: list[str], deadline_seconds: float = 20.0) -> FetchOutcome:
        outcome = FetchOutcome()

        # Only Python is measured and the rail files are read as prose, so
        # nothing else is worth a request.
        wanted = [p for p in paths if p.endswith(".py") or p.endswith(_RAIL_SUFFIXES)]
        for path in wanted:
            if self._url(path) is None:
                outcome.skipped += 1
        wanted = [p for p in wanted if self._url(path) is not None]

        if len(wanted) > self._max_files:
            # Shallow paths first: real code and a README live near the top.
            wanted = sorted(wanted, key=lambda p: (p.count("/"), p))[: self._max_files]
            outcome.skipped += 1
        if not wanted:
            return outcome

        semaphore = asyncio.Semaphore(self._concurrency)

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "ContextForge-HealthScan"},
        ) as client:

            async def one(path: str) -> None:
                url = self._url(path)
                if url is None:  # pragma: no cover - filtered above
                    return
                async with semaphore:
                    try:
                        response = await client.get(url)
                        outcome.attempted += 1
                        if response.status_code != 200:
                            outcome.failed += 1
                            return
                        text = response.text
                        if not text.strip() or "\x00" in text:
                            outcome.failed += 1
                            return
                        outcome.files[path] = text[: self._max_bytes]
                    except Exception as exc:
                        outcome.attempted += 1
                        outcome.failed += 1
                        logger.debug("health: fetch failed for %s (%s)", path, exc)

            try:
                await asyncio.wait_for(
                    asyncio.gather(*(one(p) for p in wanted)),
                    timeout=deadline_seconds,
                )
            except TimeoutError:
                # A partial result is still a usable one; the report records how
                # many files could not be read.
                outcome.failed += max(0, len(wanted) - len(outcome.files) - outcome.failed)
                logger.warning("health: fetch phase hit its %ss deadline", deadline_seconds)

        logger.info(
            "health: fetched %d/%d file(s) from %s/%s@%s (%d failed)",
            len(outcome.files),
            len(wanted),
            self._owner,
            self._repo,
            self._branch,
            outcome.failed,
        )
        return outcome
