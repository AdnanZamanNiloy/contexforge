"""Dependency advisories from OSV.dev.

This is the axis semgrep does not have at all: it matches code patterns, so it
cannot tell you that a version you depend on has a published advisory.  For a
report about somebody else's repository that is usually the most actionable
finding there is -- "you pin ``pillow 11.3.0``, GHSA-45hq-…, fixed in 12.3.0" is
a concrete, closable task, where a possible injection site is a maybe.

Two things make this safe to run on every scan.

**It is optional.**  OSV is a network service.  No network means the view says
the advisories were not checked, never that there are none.

**It is bounded and cached.**  Only declared runtime dependencies are queried,
in capped batches, and a negative result is remembered: an advisory database
does not change between two scans of the same lockfile, so re-asking is waste.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from app.security.models import Finding

__all__ = [
    "AdvisoryOutcome",
    "AdvisoryResult",
    "check_dependencies",
    "clean_version",
    "fixed_of",
    "severity_of",
]

logger = logging.getLogger(__name__)

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"
REQUEST_TIMEOUT_SECONDS = 12.0
#: OSV's own guidance is to keep batches modest; a single very large body is
#: both slow and more likely to be refused.
BATCH_SIZE = 40
#: Only runtime dependencies are advisories worth surfacing: a dev-only package
#: that is never shipped does not put the product at risk.
MAX_DEPENDENCIES = 250
MAX_ADVISORIES_PER_PACKAGE = 6
#: Several concurrent requests is plenty and keeps the scan quick; more would
#: look like abuse of a free public service.
MAX_CONCURRENCY = 4

#: Our package manager names -> OSV ecosystem names.  A dependency whose manager
#: is not in this table is not checked, and the report says so rather than
#: implying it was clear.
_ECOSYSTEMS: dict[str, str] = {
    "pip": "PyPI",
    "PEP 621 / Poetry": "PyPI",
    "Poetry": "PyPI",
    "Pipenv": "PyPI",
    "setuptools": "PyPI",
    "Conda": "PyPI",
    "npm": "npm",
    "Yarn": "npm",
    "pnpm": "npm",
    "Bun": "npm",
    "Go modules": "Go",
    "Cargo": "crates.io",
    "Bundler": "RubyGems",
    "Composer": "Packagist",
    "Maven": "Maven",
    "Gradle": "Maven",
    "NuGet": "NuGet",
    "Mix": "Hex",
    "Hex": "Hex",
}

#: Version specifiers that name no version, so no advisory can be matched.
_UNRESOLVED = {"", "*", "latest", "none", "unknown"}


@dataclass
class AdvisoryOutcome:
    """The result of asking about one dependency."""

    name: str
    version: str | None
    ecosystem: str | None
    advisories: list[Finding]
    #: The raw OSV records, kept so a repeat scan can reuse them without
    #: asking again: an advisory database does not change between two scans of
    #: the same lockfile.
    records: list[dict] = None  # type: ignore[assignment]
    error: str = ""


@dataclass
class AdvisoryResult:
    """The whole dependency check, including what it could not do."""

    outcomes: list[AdvisoryOutcome]
    checked: int
    vulnerable: int
    unchecked: int
    error: str = ""

    @property
    def findings(self) -> list[Finding]:
        """Every advisory from every dependency, as one list."""
        return [finding for outcome in self.outcomes for finding in outcome.advisories]


def clean_version(version: str | None) -> str | None:
    """A version OSV can be asked about, or ``None`` if it names none.

    The tech stack scan already reduces a specifier to a concrete version, so
    this is a second line of defence.  A range that survives is reduced to its
    lower bound rather than passed on: asking OSV about ``^1.2.3`` would match
    nothing and report a clean dependency, which is worse than not asking.
    """
    if not version:
        return None
    value = version.strip()
    if not value or value.lower() in _UNRESOLVED or any(ch in value for ch in ("/", ":", "*")):
        return None
    # Leading operators, then a whitespace-separated `>=1.2,<2` style range.
    value = re.sub(r"^(?:[=~^<>!]{1,2}\s*)+", "", value).strip()
    value = re.split(r"[\s,]+", value)[0]
    value = re.sub(r"^[vV](?=\d)", "", value)
    if not re.fullmatch(r"\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.]+)?", value):
        return None
    return value


def severity_of(record: dict) -> str:
    """The advisory's severity, from the cleanest source available.

    GitHub's reviewed advisories carry a plain label, which is what a reader can
    act on.  Otherwise the CVSS vector is read for its impact triple, which is an
    approximation and is treated as one: an advisory that cannot be rated stays
    ``unknown`` rather than being quietly rounded down to ``low``.
    """
    label = (record.get("database_specific") or {}).get("severity")
    if isinstance(label, str) and label:
        return {"MODERATE": "medium", "CRITICAL": "critical", "HIGH": "high", "LOW": "low"}.get(
            label.upper(), "unknown"
        )

    for entry in record.get("severity") or ():
        score = entry.get("score") or ""
        if not score.startswith("CVSS:"):
            continue
        # CVSS v3 spells the impact triple C/I/A; v4 uses VC/VI/VA.
        metrics = dict(part.split(":", 1) for part in score.split("/")[1:] if ":" in part)
        impacts = [metrics.get("C"), metrics.get("I"), metrics.get("A")]
        impacts += [metrics.get("VC"), metrics.get("VI"), metrics.get("VA")]
        impacts = [value for value in impacts if value]
        if not impacts:
            continue
        if "H" in impacts:
            return "high"
        if "L" in impacts:
            return "medium"
        return "low"
    return "unknown"


def fixed_of(record: dict) -> str | None:
    """The first version that resolves the advisory, when there is one."""
    best: str | None = None
    for affected in record.get("affected") or ():
        for entry in affected.get("ranges") or ():
            for event in entry.get("events") or ():
                fixed = event.get("fixed")
                # Several fixed versions appear when an advisory is split across
                # ranges; the earliest is the one to move to.
                if fixed and (best is None or fixed < best):
                    best = fixed
    return best


def _aliases(record: dict) -> str:
    aliases = [a for a in record.get("aliases") or () if a != record.get("id")]
    return ", ".join(aliases[:2])


def _to_finding(record: dict, name: str, version: str | None) -> Finding:
    advisory_id = str(record.get("id") or "")
    fixed = fixed_of(record)
    detail = (record.get("summary") or record.get("details") or "").strip().split("\n")[0][:280]
    if fixed:
        detail = f"{detail} Fixed in {fixed}." if detail else f"Fixed in {fixed}."
    aliases = _aliases(record)
    if aliases:
        detail = f"{detail} ({aliases})".strip()
    cwes = (record.get("database_specific") or {}).get("cwe_ids") or []
    return Finding(
        id=f"advisory:{advisory_id}",
        title=f"{name} {version or 'unresolved'} — {advisory_id}",
        severity=severity_of(record),
        category="Vulnerable dependency",
        detail=detail,
        location=name,
        source="dependency",
        # A published advisory is a fact, not a pattern that might match.
        confidence="high",
        cwe=str(cwes[0]) if cwes else "",
        reference=f"https://osv.dev/vulnerability/{advisory_id}" if advisory_id else "",
        extra={
            "advisory_id": advisory_id,
            "package": name,
            "installed_version": version,
            "fixed_version": fixed,
        },
    )


async def _query_one(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, name: str, version: str, ecosystem: str
) -> AdvisoryOutcome:
    payload = {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
    async with semaphore:
        try:
            response = await client.post(OSV_QUERY_URL, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            # A 4xx for one package is that package's problem, not the scan's.
            message = f"OSV rejected the query for {name}"
            if exc.response.status_code == 429:
                message = "OSV is rate limiting this scan"
            return AdvisoryOutcome(name, version, ecosystem, [], error=message)
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("security: OSV query failed for %s: %s", name, exc)
            return AdvisoryOutcome(name, version, ecosystem, [], error=f"OSV query failed for {name}")

    records = data.get("vulns") or []
    findings = [_to_finding(record, name, version) for record in records[:MAX_ADVISORIES_PER_PACKAGE]]
    if len(records) > MAX_ADVISORIES_PER_PACKAGE:
        logger.info("security: %s has %d advisories, showing %d", name, len(records), MAX_ADVISORIES_PER_PACKAGE)
    return AdvisoryOutcome(name, version, ecosystem, findings, records)


async def check_dependencies(
    dependencies: list[dict],
    cache: dict[tuple[str, str, str], list[dict]] | None = None,
) -> AdvisoryResult:
    """Ask OSV about each declared runtime dependency.

    *dependencies* are the rows the tech stack scan already produced, so this
    costs no extra parsing.  *cache* maps ``(name, version, ecosystem)`` to the
    raw advisory records seen last time, so an unchanged lockfile is not
    re-queried.
    """
    cache = cache if cache is not None else {}
    queryable: list[tuple[str, str, str]] = []
    unchecked = 0

    seen: set[tuple[str, str, str]] = set()
    for row in dependencies[:MAX_DEPENDENCIES]:
        if row.get("scope") == "dev":
            # A dev-only dependency is not shipped, so its advisories are not
            # this repository's risk.
            continue
        ecosystem = _ECOSYSTEMS.get(row.get("manager") or "")
        if not ecosystem:
            unchecked += 1
            continue
        version = clean_version(row.get("version"))
        if not version:
            unchecked += 1
            continue
        key = (row["name"], version, ecosystem)
        if key in seen:
            continue
        seen.add(key)
        queryable.append(key)

    outcomes: list[AdvisoryOutcome] = []
    errors: list[str] = []

    to_query = []
    for key in queryable:
        cached = cache.get(key)
        if cached is None:
            to_query.append(key)
            continue
        name, version, ecosystem = key
        outcomes.append(
            AdvisoryOutcome(
                name,
                version,
                ecosystem,
                [_to_finding(record, name, version) for record in cached[:MAX_ADVISORIES_PER_PACKAGE]],
                cached,
            )
        )

    if to_query:
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            results = await asyncio.gather(
                *(_query_one(client, semaphore, name, version, ecosystem) for name, version, ecosystem in to_query)
            )
        for key, outcome in zip(to_query, results, strict=True):
            if outcome.error:
                errors.append(outcome.error)
                continue
            cache[key] = outcome.records or []
            outcomes.append(outcome)

    findings = [finding for outcome in outcomes for finding in outcome.advisories]
    vulnerable = {finding.location for finding in findings}
    error = ""
    if errors:
        # One message, not one per package: a rate-limited OSV is one fact.
        unique = sorted(set(errors))
        error = unique[0] if len(unique) == 1 else f"{len(unique)} dependency lookups failed"

    return AdvisoryResult(
        outcomes=outcomes,
        checked=len(outcomes),
        vulnerable=len(vulnerable),
        unchecked=unchecked,
        error=error,
    )
