"""Language and technology detection for the Dependency & Tech Stack scan.

Two ideas are carried over from stack-analyser:

* a technology is present when **either** a manifest/lockfile by its name
  exists **or** a dependency by its name is declared in some manifest, and
* languages come from a histogram of file extensions.

Its 4,300-line copy of GitHub Linguist is not carried over: language detection
here is a curated extension table, which is enough to rank the languages a
repository is actually written in without loading a 645-entry catalogue.  The
*rule* tree is a different matter -- :mod:`app.techstack.rules` carries 282 of
its rules, generated from its own source, so the database, hosting, CI, cloud
and AI categories are complete rather than sampled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.techstack.manifests import SOURCE_KINDS
from app.techstack.models import normalise_path
from app.techstack.rules import COMPONENT_KINDS, RULES, build_index

__all__ = [
    "COMPONENT_KINDS",
    "LANGUAGES",
    "detect_technologies",
    "language_histogram",
    "languages_for_path",
    "summarise",
]


@dataclass(frozen=True)
class Language:
    name: str
    extensions: frozenset[str]
    #: Data/config formats are reported separately: they are not "written in"
    #: by the project the way a programming language is.
    kind: str = "programming"


def _lang(name: str, kind: str = "programming", *exts: str) -> Language:
    return Language(name, frozenset(e.lower() for e in exts), kind)


# Extensions are matched against the file suffix only, so a multi-part suffix
# such as ".d.ts" is listed explicitly where it matters.
LANGUAGES: tuple[Language, ...] = (
    _lang("Python", "programming", ".py", ".pyi", ".pyw"),
    _lang("TypeScript", "programming", ".ts", ".tsx", ".mts", ".cts", ".d.ts"),
    _lang("JavaScript", "programming", ".js", ".jsx", ".mjs", ".cjs"),
    _lang("Go", "programming", ".go"),
    _lang("Rust", "programming", ".rs"),
    _lang("Java", "programming", ".java"),
    _lang("Kotlin", "programming", ".kt", ".kts"),
    _lang("Scala", "programming", ".scala", ".sc"),
    _lang("Ruby", "programming", ".rb", ".rake", ".gemspec"),
    _lang("PHP", "programming", ".php", ".phtml"),
    _lang("C", "programming", ".c", ".h"),
    _lang("C++", "programming", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"),
    _lang("C#", "programming", ".cs", ".csx"),
    _lang("Swift", "programming", ".swift"),
    _lang("Objective-C", "programming", ".m", ".mm"),
    _lang("Dart", "programming", ".dart"),
    _lang("Elixir", "programming", ".ex", ".exs"),
    _lang("Erlang", "programming", ".erl", ".hrl"),
    _lang("Haskell", "programming", ".hs"),
    _lang("Lua", "programming", ".lua"),
    _lang("Perl", "programming", ".pl", ".pm"),
    _lang("R", "programming", ".r", ".R"),
    _lang("Julia", "programming", ".jl"),
    _lang("Zig", "programming", ".zig"),
    _lang("Shell", "programming", ".sh", ".bash", ".zsh", ".fish"),
    _lang("Vue", "programming", ".vue"),
    _lang("Svelte", "programming", ".svelte"),
    _lang("HTML", "markup", ".html", ".htm"),
    _lang("CSS", "markup", ".css", ".scss", ".sass", ".less"),
    _lang("SQL", "data", ".sql"),
    _lang("Shell", "data", ".sh"),
    _lang("Dockerfile", "data", ".dockerfile"),
    _lang("YAML", "data", ".yml", ".yaml"),
    _lang("JSON", "data", ".json"),
    _lang("TOML", "data", ".toml"),
    _lang("INI", "data", ".ini", ".cfg", ".conf"),
    _lang("Markdown", "prose", ".md", ".markdown", ".mdx"),
    _lang("RST", "prose", ".rst"),
)


# Managers detected purely from a lockfile or manifest existing, since they
# declare no dependency of their own.
_MANAGER_FILES: dict[str, str] = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "yarn.lock": "Yarn",
    "pnpm-lock.yaml": "pnpm",
    "bun.lock": "Bun",
    "poetry.lock": "Poetry",
    "Pipfile.lock": "Pipenv",
    "Pipfile": "Pipenv",
    "requirements.txt": "pip",
    "go.mod": "Go modules",
    "go.sum": "Go modules",
    "Cargo.lock": "Cargo",
    "Cargo.toml": "Cargo",
    "Gemfile.lock": "Bundler",
    "Gemfile": "Bundler",
    "composer.lock": "Composer",
    "composer.json": "Composer",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "mix.exs": "Mix",
    "rebar.config": "Rebar3",
    "packages.config": "NuGet",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "Chart.yaml": "Helm",
}

_SKIP_DIR = re.compile(
    r"(^|/)(node_modules|\.git|dist|build|target|vendor|__pycache__|\.venv|venv|"
    r"site-packages|coverage|\.next|\.nuxt|out|bower_components|jspm_packages|\.tox|"
    r"\.mypy_cache|\.pytest_cache|\.gradle|\.terraform|third_party|thirdparty)(/|$)",
    re.IGNORECASE,
)
_SKIP_FILE = re.compile(r"(\.min\.(js|css)$)|(\.map$)|(-lock\.json$)|(\.snap$)", re.IGNORECASE)


def _extension_of(path: str) -> str | None:
    base = path.rsplit("/", 1)[-1]
    # Multi-part suffixes first, so ".d.ts" beats ".ts".
    for candidate in (".d.ts", ".d.mts", ".d.cts"):
        if base.lower().endswith(candidate):
            return candidate
    if "." not in base:
        return None
    return base[base.rfind(".") :].lower()


def languages_for_path(path: str) -> list[dict]:
    """The languages a single path contributes, as at most one row.

    A file has one extension, so this is one language or nothing.  It exists so
    the service graph can count languages per service: the repository-wide
    histogram says a project is 60% TypeScript, but not which of its services.
    """
    ext = _extension_of(path)
    if not ext:
        return []
    for language in LANGUAGES:
        if ext in language.extensions:
            return [{"name": language.name, "kind": language.kind, "files": 1}]
    return []


def language_histogram(paths: list[str]) -> list[dict]:
    """Count files per language across *paths*, ignoring vendored and built trees.

    Vendored and generated directories are skipped outright: without that,
    ``node_modules`` alone would dominate the histogram of any real project.
    """
    counts: dict[tuple[str, str], int] = {}
    for path in paths:
        if _SKIP_DIR.search(path) or _SKIP_FILE.search(path):
            continue
        for row in languages_for_path(path):
            key = (row["name"], row["kind"])
            counts[key] = counts.get(key, 0) + row["files"]

    total = sum(counts.values())
    rows = [
        {
            "name": name,
            "kind": kind,
            "files": count,
            # Rounded so the client can render a bar without re-deriving the ratio.
            "share": round(count / total, 4) if total else 0.0,
        }
        for (name, kind), count in counts.items()
    ]
    # Most present first; data formats last so a repo with many YAML files does
    # not appear to be a YAML project.  `kind != "programming"` sorts programming
    # languages ahead of data and prose formats.
    rows.sort(key=lambda row: (row["kind"] != "programming", -row["files"], row["name"]))
    return rows


#: Built once at import: the rule table is static, and rebuilding the index per
#: scan would recompile every pattern for nothing.
_INDEX = build_index(RULES)


def match_rules(name: str, manager: str) -> list:
    """Rules that *name* declares as evidence of *manager*'s technology.

    Both index levels are consulted: a literal dependency name, and a regular
    expression carried over from stack-analyser (an AWS SDK client is any name
    starting ``@aws-sdk/``, so those rules are patterns rather than literals).
    A rule fires only if it also applies to the declaring package manager, which
    is what keeps a ``redis`` in a Go project from being reported as a Python
    client while still letting a Terraform ``aws_s3_bucket`` light up AWS.
    """
    found: list = []
    seen: set[str] = set()

    for rule in _INDEX.exact.get(name.lower(), ()):
        if rule.key not in seen and rule.matches_manager(manager):
            seen.add(rule.key)
            found.append(rule)

    for entry in _INDEX.patterns:
        if entry.rule.key in seen or not entry.rule.matches_manager(manager):
            continue
        # The shared literal prefix of an anchored rule is a sound prefilter.
        if entry.prefix and not name.startswith(entry.prefix):
            continue
        if any(pattern.search(name) for pattern in entry.patterns):
            seen.add(entry.rule.key)
            found.append(entry.rule)
    return found


def match_path(path: str) -> list:
    """Rules for which *path* is evidence, by file name or directory name.

    This is the other half of stack-analyser's two-tier rule, and for CI and
    hosting it is the half that matters: CircleCI is declared by a
    ``.circleci/config.yml`` and nothing else, Jenkins by a ``Jenkinsfile``,
    Vercel by a ``vercel.json``.  No manifest in the repository names them.
    """
    path = normalise_path(path)
    found: dict[str, object] = {}

    for segment in path.split("/"):
        for rule in _INDEX.files.get(segment, ()):
            found[rule.key] = rule
    basename = path.rsplit("/", 1)[-1]
    for rule in _INDEX.files.get(basename, ()):
        found[rule.key] = rule

    for prefix, rules in _INDEX.file_prefixes:
        if path.startswith(prefix + "/") or path == prefix or ("/" + prefix + "/") in ("/" + path + "/"):
            for rule in rules:
                found[rule.key] = rule

    return list(found.values())


def detect_technologies(
    manifest_results,
    package_managers: list[str],
    paths: list[str] | None = None,
) -> list[dict]:
    """Match declared dependencies and repository files against the rule table.

    A rule fires when a dependency name matches and its declaring package
    manager is one the rule applies to, which keeps a stray ``redis`` in a Go
    project from being reported as a Python client; or when a file the rule
    names is present, which is how CI and hosting are actually declared.
    """
    managers = set(package_managers)
    found: dict[str, dict] = {}

    def record(rule, manager: str | None, version: str | None, dependency: str | None) -> None:
        entry = found.get(rule.name)
        if entry is None:
            entry = found[rule.name] = {
                "name": rule.name,
                "key": rule.key,
                "kind": rule.kind,
                "version": version,
                "managers": [],
                "dependency": dependency,
                "evidence": [],
                "dependency_names": [],
            }
        if manager and manager not in entry["managers"]:
            entry["managers"].append(manager)
        # Prefer a concrete version when one manifest had it and another did not.
        if not entry["version"] and version:
            entry["version"] = version
        if dependency and dependency not in entry["dependency_names"]:
            entry["dependency_names"].append(dependency)
        if len(entry["evidence"]) < 6:
            marker = f"{dependency} ({manager})" if dependency else (manager or "file")
            if marker not in entry["evidence"]:
                entry["evidence"].append(marker)

    for result in manifest_results:
        for dep in result.dependencies:
            for rule in match_rules(dep.name, result.manager):
                # Several rules can share a display name; the first one to fire
                # wins so a technology is not listed twice under one heading.
                record(rule, result.manager, dep.version, dep.name)

    # File evidence: which rule matched, and where.
    for path in paths or ():
        for rule in match_path(path):
            record(rule, None, None, None)
            marker = path
            if marker not in found[rule.name]["evidence"] and len(found[rule.name]["evidence"]) < 6:
                found[rule.name]["evidence"].append(marker)

    # Sources inferred from a manifest are reported too: a repo can use npm
    # without depending on anything that names it.
    for manager in sorted(managers):
        if manager not in {m for entry in found.values() for m in entry["managers"]}:
            found[manager] = {
                "name": manager,
                # Namespaced so it cannot collide with a real tech key.
                "key": f"manager:{manager}",
                "kind": SOURCE_KINDS.get(manager, "Package manager"),
                "version": None,
                "managers": [manager],
                "dependency": None,
                "evidence": [manager],
                "dependency_names": [],
            }

    rows = list(found.values())
    rows.sort(key=lambda row: (row["kind"], row["name"].lower()))
    return rows


def summarise(
    languages: list[dict],
    technologies: list[dict],
    package_managers: list[str],
    manifest_count: int,
    dependency_count: int,
) -> str:
    """One or two sentences describing the stack, for the report header."""
    if not languages and not technologies:
        return "No manifests or recognisable source files were found in this repository."

    primary = [row["name"] for row in languages if row["kind"] == "programming"][:3]
    parts: list[str] = []
    if primary:
        parts.append(f"Written primarily in {', '.join(primary)}")
    frameworks = [row["name"] for row in technologies if row["kind"] in ("Framework", "UI framework")]
    if frameworks:
        parts.append(f"using {', '.join(frameworks[:3])}")
    if package_managers:
        parts.append(f"dependencies managed by {', '.join(package_managers[:3])}")
    sentence = "; ".join(parts) if parts else "A small repository"

    # The tail is joined rather than appended with its own full stop, so the
    # summary always ends in exactly one period.
    tail: str | None = None
    if manifest_count and dependency_count:
        plural = "" if manifest_count == 1 else "s"
        tail = f"{dependency_count} dependencies declared across {manifest_count} manifest{plural}"
    elif not manifest_count:
        tail = "No dependency manifests were found"
    if tail:
        sentence = f"{sentence}. {tail}"
    return sentence + "."
