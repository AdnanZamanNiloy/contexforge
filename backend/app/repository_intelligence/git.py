"""Safe git operations for Repository Intelligence.

The repository is cloned with ``git clone`` into a private temp directory
under ``settings.REPO_ANALYSIS_DIR``.  Only *git* subprocesses ever run:
no repository code, scripts, hooks, or build steps are executed.  The clone
is removed in ``close()``.

History is extracted with bounded ``git log`` invocations so analysis stays
reasonable on CPU-only hardware.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings
from observability.tracer import observe

__all__ = ["GitRepoError", "GitRepository"]

logger = logging.getLogger(__name__)

_GIT_URL_RE = re.compile(r"^(?:https?://github\.com/)?([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")
_WINDOW_DAYS = {"30d": 30, "90d": 90, "180d": 180, "365d": 365, "all": None}


class GitRepoError(RuntimeError):
    """Raised when cloning or analysing the repository fails."""


def parse_repo_id(url: str) -> tuple[str, str]:
    """Return ``(owner, name)`` from a GitHub repository URL or 'owner/name'."""
    match = _GIT_URL_RE.match(url.strip())
    if not match:
        raise GitRepoError(f"'{url}' is not a recognised GitHub repository.")
    return match.group(1), match.group(2)


class GitRepository:
    """Bounded clone + read-only git analysis of a remote repository.

    Args:
        repo_url: repository URL or ``owner/name``.
        branch:   branch to clone; default branch when ``None``.
    """

    def __init__(self, repo_url: str, branch: str | None = None) -> None:
        self.repo_url = repo_url
        self.branch = branch
        self._base = Path(settings.REPO_ANALYSIS_DIR)
        self._workdir: Path | None = None
        self._temporary = False
        # A local git checkout may be supplied directly (used by tests and by
        # the self-analysis path); in that case nothing is cloned.  When a
        # local directory is provided the owner/name are derived from the URL.
        local = Path(repo_url)
        if local.is_dir():
            self._workdir = local
            self._temporary = False
            self.owner, self.name = "local", local.name
        else:
            self.owner, self.name = parse_repo_id(repo_url)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="repo_git_clone")
    async def clone(self) -> None:
        """Clone the repository into a private temp directory.

        If the source is already a local git checkout it is used as-is.
        """
        if self._workdir is not None:
            logger.info("Using existing local checkout: %s", self._workdir)
            return
        self._base.mkdir(parents=True, exist_ok=True)
        self._workdir = Path(tempfile.mkdtemp(prefix=f"{self.name}-", dir=str(self._base)))
        self._temporary = True
        cmd = ["git", "clone", "--quiet"]
        if self.branch:
            cmd += ["--branch", self.branch, "--single-branch"]
        # A shallow clone (--depth 1) makes ``git log`` see only the tip commit,
        # so commit history / churn / ownership come back empty.  Fetch full
        # history instead so Git History, file churn and ownership are useful.
        cmd += [self.repo_url, str(self._workdir)]
        await self._run(cmd, timeout=settings.REPO_CLONE_TIMEOUT)
        logger.info("git clone complete: %s/%s -> %s", self.owner, self.name, self._workdir)

    @property
    def workdir(self) -> Path:
        if self._workdir is None:
            raise GitRepoError("Repository has not been cloned yet.")
        return self._workdir

    @property
    def default_branch(self) -> str:
        """Best-effort detection of the remote's default branch.

        Falls back to ``branch``, then ``main``.
        """
        if not self.workdir.exists():
            return self.branch or "main"
        try:
            out = subprocess.run(
                ["git", "symbolic-ref", "--short", "--quiet", "refs/remotes/origin/HEAD"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            if out and out.startswith("origin/"):
                return out.split("origin/", 1)[1]
        except Exception:  # pragma: no cover - defensive
            pass
        return self.branch or "main"

    @observe(name="repo_git_head")
    async def head_commit(self) -> str:
        out = await self._run(["git", "rev-parse", "HEAD"], cwd=self.workdir, quiet=True)
        return out.strip()

    @observe(name="repo_git_meta")
    async def repository_meta(self) -> dict[str, Any]:
        """Return descriptive metadata about the checked-out repo."""
        out = await self._run(
            ["git", "log", "-1", "--format=%s|%H|%an|%ad", "--date=iso8601"],
            cwd=self.workdir,
            quiet=True,
        )
        msg, sha, author, iso = out.strip().split("|", 3)
        return {"message": msg, "sha": sha, "author": author, "iso": iso}

    @observe(name="repo_git_branches")
    async def branches(self) -> list[dict[str, Any]]:
        out = await self._run(["git", "branch", "-r", "--format=%(refname:short)"], cwd=self.workdir, quiet=True)
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line in {"origin/HEAD"}:
                continue
            name = line.replace("origin/", "", 1)
            count = await self._commit_count(name)
            rows.append(
                {
                    "name": name,
                    "commits": count,
                    "active": name in {"main", "master"} or name == self.branch,
                }
            )
        return rows

    @observe(name="repo_git_commits")
    async def commits(self, window: str = "180d", limit: int = 500) -> list[dict[str, Any]]:
        since = self._since_arg(window)
        fmt = "%H|%an|%ad|%s"
        cmd = ["git", "log", "--no-merges", f"--format={fmt}", "--date=iso8601"]
        if since:
            cmd += [f"--since={since}"]
        if limit:
            cmd += [f"--max-count={limit}"]
        out = await self._run(cmd, cwd=self.workdir, quiet=True)
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            sha, author, iso, message = parts
            try:
                dt = datetime.fromisoformat(iso)
            except ValueError:
                dt = datetime.now(UTC)
            rows.append({"sha": sha, "author": author, "message": message, "time": dt})
        return rows

    @observe(name="repo_git_shortlog")
    async def contributors(self, window: str = "180d") -> list[dict[str, Any]]:
        since = self._since_arg(window)
        cmd = ["git", "shortlog", "-sne", "--no-merges"]
        if since:
            cmd += [f"--since={since}"]
        # Explicit HEAD: shortlog reads piped stdin otherwise (non-tty).
        cmd += ["HEAD"]
        out = await self._run(cmd, cwd=self.workdir, quiet=True)
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            count, _, ident = line.partition("\t")
            email = ident.rsplit(" ", 1)[-1].strip("<>")
            name = ident.rsplit(" ", 1)[0]
            rows.append({"name": name or email, "email": email, "commits": int(count)})
        return rows

    @observe(name="repo_git_file_churn")
    async def file_churn(self, window: str = "180d", limit: int = 100) -> list[dict[str, Any]]:
        since = self._since_arg(window)
        cmd = ["git", "log", "--no-merges", "--name-only", "--pretty=format:"]
        if since:
            cmd += [f"--since={since}"]
        out = await self._run(cmd, cwd=self.workdir, quiet=True)
        counts: dict[str, int] = {}
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            counts[line] = counts.get(line, 0) + 1
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [{"name": name, "value": count} for name, count in top]

    @observe(name="repo_git_ownership")
    async def ownership(self, window: str = "180d") -> dict[str, Any]:
        """Estimate per-path ownership from the commit author counts."""
        since = self._since_arg(window)
        cmd = ["git", "log", "--no-merges", "--name-only", "--pretty=format:%an"]
        if since:
            cmd += [f"--since={since}"]
        out = await self._run(cmd, cwd=self.workdir, quiet=True)
        authors: dict[str, int] = {}
        files: dict[str, dict[str, int]] = {}
        current = None
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            if line in authors or current is None:
                if line not in authors:
                    current = line
                    authors.setdefault(line, 0)
                else:
                    authors[current] += 1
            else:
                bucket = files.setdefault(line, {})
                bucket[current] = bucket.get(current, 0) + 1
        return {"authors": authors, "files": files}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _commit_count(self, branch: str) -> int:
        out = await self._run(
            ["git", "rev-list", "--count", f"origin/{branch}"], cwd=self.workdir, quiet=True, allow_fail=True
        )
        try:
            return int(out.strip() or 0)
        except ValueError:
            return 0

    def _since_arg(self, window: str) -> str | None:
        days = _WINDOW_DAYS.get(window)
        if days is None or settings.REPO_GIT_HISTORY_FULL:
            return None
        return f"{days} days ago"

    async def _run(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
        quiet: bool = False,
        allow_fail: bool = False,
    ) -> str:
        """Run a git subprocess without a shell and without exposing secrets."""
        if cwd is None:
            cwd = self.workdir
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout or 30)
            except TimeoutError:
                os.killpg(os.getpgid(proc.pid), 15)
                raise GitRepoError(f"git command timed out: {' '.join(cmd)}") from None
        except FileNotFoundError as exc:
            raise GitRepoError(f"git binary not found: {exc}") from exc

        if proc.returncode != 0 and not allow_fail:
            err = stderr.decode(errors="ignore").strip()
            raise GitRepoError(f"git failed ({cmd[1]}): {err}")
        out = stdout.decode(errors="ignore")
        if not quiet and out.strip():
            logger.debug("git> %s", " ".join(cmd))
        return out

    def close(self) -> None:
        """Remove the cloned working tree if it was a temporary clone."""
        if self._workdir is not None and self._temporary and self._workdir.exists():
            try:
                shutil.rmtree(self._workdir, ignore_errors=True)
                logger.info("Removed repo clone: %s", self._workdir)
            except OSError:
                pass
        self._workdir = None
        self._temporary = False
