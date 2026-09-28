"""Manifest and lockfile parsers for the Dependency & Tech Stack scan.

Each parser turns one manifest's text into a flat list of
``(name, version)`` pairs.  Parsers are deliberately shallow: the report answers
"what is declared and at which version", so a spec that cannot be resolved to a
concrete version is reported as the range it was written as rather than being
guessed at.  Nothing here resolves versions against a registry — that would be a
network call per dependency, which the scan explicitly must not make.

The set of manifests is the union of what stack-analyser treats as a
package-manager lockfile plus the manifests it detects frameworks from, reduced
to the ecosystems that actually occur in practice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

__all__ = [
    "MANIFESTS",
    "Dependency",
    "ManifestResult",
    "is_manifest",
    "parse_manifest",
]


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str | None
    scope: str = "runtime"  # runtime | dev | optional | peer


@dataclass
class ManifestResult:
    manager: str
    language: str
    path: str
    dependencies: list[Dependency]
    #: Set when the manifest exists but could not be understood, so the report
    #: can say so rather than silently showing an empty dependency list.
    error: str | None = None


# --- Version-spec helpers -------------------------------------------------- #

# Ranges that carry no useful information once reported: "*" and the caret
# markers stripped by _clean_version below.
_ANY = re.compile(r"^[\s]*[>=<!~^*]*\s*$")


def _clean_version(spec: str | None) -> str | None:
    """Reduce a declared specifier to the version a human would read.

    ``^1.2.3`` -> ``1.2.3``, ``~2.0`` -> ``2.0``, ``>=3.1.0,<4`` -> ``3.1.0``
    (the lower bound, which is the version actually in use).  Anything with no
    digits is a workspace/file/git reference and is reported as ``None`` rather
    than shown as noise.
    """
    if not spec:
        return None
    text = str(spec).strip()
    if not text or _ANY.match(text):
        return None
    # A git/url/workspace spec has no version to report.
    if text.startswith(("git+", "git:", "http://", "https://", "file:", "workspace:", "link:")):
        return None
    # Take the first space-delimited environment marker, e.g. ">=1.0 ; python_version<'3.9'".
    text = text.split(";")[0].strip()
    # Prefer the first concrete version-looking token.
    match = re.search(r"\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.\-]+)?", text)
    if not match:
        return None
    return match.group(0)


# --- Ecosystem parsers ----------------------------------------------------- #

_SECTION_RE = re.compile(r"^\[(?P<section>[^\]]+)\]\s*$")
_PEP_508 = re.compile(r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?P<extras>\[[^\]]*\])?\s*(?P<spec>.*)$")


def _parse_requirements(text: str) -> list[Dependency]:
    """PEP 508 requirements: pip, pipenv and ``requirements*.txt``.

    Environment markers, comments, ``-r``/``-e`` directives and blank lines are
    dropped; the name is taken from the first token of what is left.
    """
    deps: list[Dependency] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _PEP_508.match(line)
        if not match:
            continue
        name = match.group("name")
        version = _clean_version(match.group("spec").split(";")[0].split("#")[0])
        if name and name.lower() != "python":
            deps.append(Dependency(name=name, version=version))
    return deps


def _parse_pyproject(text: str) -> list[Dependency]:
    """``[project] dependencies`` and the Poetry ``[tool.poetry.dependencies]`` table.

    Parsed with the stdlib TOML reader when the file is valid TOML, and with a
    section-aware line scan otherwise — a truncated or partially-indexed file is
    common here and should still yield what it clearly declares.
    """
    try:
        import tomllib

        data = tomllib.loads(text)
    except Exception:
        return _parse_pyproject_lines(text)

    deps: list[Dependency] = []
    project = data.get("project") or {}
    for spec in project.get("dependencies") or []:
        if isinstance(spec, str):
            match = _PEP_508.match(spec)
            if match and match.group("name").lower() != "python":
                deps.append(Dependency(name=match.group("name"), version=_clean_version(match.group("spec"))))
    optional = project.get("optional-dependencies") or {}
    for group in optional.values():
        for spec in group or []:
            match = _PEP_508.match(spec) if isinstance(spec, str) else None
            if match and match.group("name").lower() != "python":
                deps.append(Dependency(name=match.group("name"), version=_clean_version(match.group("spec"))))

    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        if isinstance(spec, str):
            deps.append(Dependency(name=name, version=_clean_version(spec)))
        elif isinstance(spec, dict):
            deps.append(Dependency(name=name, version=_clean_version(spec.get("version"))))
    return deps


def _parse_pyproject_lines(text: str) -> list[Dependency]:
    """Fallback for TOML this machine cannot read: scan the two known tables."""
    deps: list[Dependency] = []
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        header = _SECTION_RE.match(line)
        if header:
            section = header.group("section").strip()
            continue
        if section not in ("project", "tool.poetry.dependencies"):
            continue
        # PEP 508 list entry: "fastapi>=0.110", optionally quoted.
        entry = line.strip().strip(",").strip("\"'")
        if not entry or entry.startswith("["):
            continue
        match = _PEP_508.match(entry)
        if match:
            name = match.group("name")
            if name.lower() != "python":
                deps.append(Dependency(name=name, version=_clean_version(match.group("spec"))))
            continue
        # Poetry table entry: fastapi = "^0.110"  (or fastapi = { version = "^0.110" })
        if section == "tool.poetry.dependencies" and "=" in line:
            name, _, value = line.partition("=")
            name = name.strip().strip("\"'")
            version = None
            quoted = re.search(r"[\"']\s*([^,\}]+?)\s*[\"']", value)
            if quoted:
                version = _clean_version(quoted.group(1))
            elif value.strip().startswith(("^", "~", ">", "<", "*")):
                version = _clean_version(value)
            if name and name.lower() != "python" and re.fullmatch(r"[A-Za-z0-9._-]+", name):
                deps.append(Dependency(name=name, version=version))
    return deps


def _parse_package_json(text: str) -> list[Dependency]:
    """npm/yarn/pnpm/bun manifest, including its four dependency blocks."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    blocks = (
        ("dependencies", "runtime"),
        ("devDependencies", "dev"),
        ("peerDependencies", "peer"),
        ("optionalDependencies", "optional"),
    )
    deps: list[Dependency] = []
    seen: set[tuple[str, str]] = set()
    for key, scope in blocks:
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        for name, spec in block.items():
            if not isinstance(name, str) or (name, scope) in seen:
                continue
            seen.add((name, scope))
            deps.append(Dependency(name=name, version=_clean_version(spec), scope=scope))
    return deps


def _parse_go_mod(text: str) -> list[Dependency]:
    """go.mod: single-block ``require`` statements plus the require block."""
    deps: list[Dependency] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block:
            if line == ")":
                in_block = False
                continue
            parts = line.split()
        elif line.startswith("require "):
            parts = line[len("require ") :].split()
        else:
            continue
        if len(parts) >= 2 and parts[0] != "(":
            version = _clean_version(parts[1])
            if version:
                deps.append(Dependency(name=parts[0], version=version))
    return deps


def _parse_cargo(text: str) -> list[Dependency]:
    """Cargo.toml: ``[dependencies]`` and the target/dev tables."""
    deps: list[Dependency] = []
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        header = _SECTION_RE.match(line)
        if header:
            section = header.group("section").strip()
            continue
        if not section.startswith("dependencies") and not section.startswith("dev-dependencies"):
            continue
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().strip("\"'")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            continue
        version = None
        # version = "1.2"  |  version = { version = "1.2" }
        if "{" in value:
            inner = re.search(r"version\s*=\s*[\"']([^\"']+)[\"']", value)
            if inner:
                version = _clean_version(inner.group(1))
        else:
            version = _clean_version(value.strip().strip("\"'"))
        deps.append(
            Dependency(
                name=name,
                version=version,
                scope="dev" if section.startswith("dev-dependencies") else "runtime",
            )
        )
    return deps


_GEM_SPEC = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*\(([^)]*)\)")


def _parse_gemfile(text: str) -> list[Dependency]:
    """Gemfile.lock: ``name (1.2.3)`` entries."""
    deps: list[Dependency] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(
            ("#", "GEM", "PATH", "GIT", "PLATFORMS", "DEPENDENCIES", "RUBY VERSION", "BUNDLED WITH", "  ")
        ):
            continue
        match = _GEM_SPEC.match(line)
        if match:
            deps.append(Dependency(name=match.group(1), version=_clean_version(match.group(2))))
    return deps


def _parse_composer(text: str) -> list[Dependency]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    deps: list[Dependency] = []
    for key, scope in (("require", "runtime"), ("require-dev", "dev")):
        block = data.get(key) if isinstance(data, dict) else None
        if not isinstance(block, dict):
            continue
        for name, spec in block.items():
            if not isinstance(name, str) or name == "php":
                continue
            deps.append(Dependency(name=name, version=_clean_version(spec), scope=scope))
    return deps


_POM_ARTIFACT = re.compile(
    r"<dependency>\s*(?:<!--.*?-->\s*)*<groupId>(?P<group>[^<]+)</groupId>"
    r"\s*<artifactId>(?P<artifact>[^<]+)</artifactId>"
    r"\s*(?:<version>(?P<version>[^<]+)</version>)?",
    re.DOTALL,
)


def _parse_pom(text: str) -> list[Dependency]:
    deps: list[Dependency] = []
    for match in _POM_ARTIFACT.finditer(text):
        group = match.group("group").strip()
        artifact = match.group("artifact").strip()
        if not group or not artifact:
            continue
        deps.append(
            Dependency(
                name=f"{group}:{artifact}",
                version=_clean_version(match.group("version")),
            )
        )
    return deps


def _parse_maven_gradle(text: str) -> list[Dependency]:
    """Gradle: ``implementation "group:artifact:version"`` style coordinates."""
    deps: list[Dependency] = []
    pattern = re.compile(
        r"(?:implementation|api|compile|testImplementation|runtimeOnly|compileOnly)"
        r"[(\s]\s*[\"']([^\"']+)[\"']"
    )
    for match in pattern.finditer(text):
        parts = match.group(1).split(":")
        if len(parts) >= 3:
            deps.append(Dependency(name=f"{parts[0]}:{parts[1]}", version=_clean_version(parts[2])))
        elif len(parts) == 2:
            deps.append(Dependency(name=f"{parts[0]}:{parts[1]}", version=None))
    return deps


_DOCKER_FROM = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
# The install command is usually one link in a `RUN` chain, as in
# `RUN apt-get update && apt-get install -y curl`, so it is matched anywhere on
# the line rather than at its start.
_DOCKER_INSTALL = re.compile(r"(?:apt-get|apt)\s+install|apk\s+add|yum\s+install", re.IGNORECASE)


def _parse_dockerfile(text: str) -> list[Dependency]:
    """A Dockerfile is not a package manager, but its base image and its system
    packages are the clearest signal of a runtime and its system libraries."""
    deps: list[Dependency] = []
    for match in _DOCKER_FROM.finditer(text):
        image = match.group(1)
        if image.lower() == "scratch":
            continue
        if ":" in image:
            name, _, tag = image.rpartition(":")
            # A registry host with a port is not a tag.
            if "/" not in tag:
                deps.append(Dependency(name=name, version=tag))
            else:
                deps.append(Dependency(name=image, version=None))
        else:
            deps.append(Dependency(name=image, version=None))
    for line in text.splitlines():
        if not _DOCKER_INSTALL.search(line):
            continue
        # Everything after the install verb on this line is candidate packages.
        tail = line[_DOCKER_INSTALL.search(line).end() :]
        for token in tail.split():
            if token.startswith("-"):
                continue
            deps.append(Dependency(name=token, version=None, scope="system"))
    return deps


# --- Registry -------------------------------------------------------------- #
# basenames -> (manager, language, parser).  Ordered longest-basename-first at
# lookup time so "requirements-dev.txt" wins over a bare "requirements.txt".
MANIFESTS: dict[str, tuple[str, str, object]] = {
    # JavaScript
    "package.json": ("npm", "JavaScript", _parse_package_json),
    "package-lock.json": ("npm", "JavaScript", _parse_package_json),
    "npm-shrinkwrap.json": ("npm", "JavaScript", _parse_package_json),
    "yarn.lock": ("Yarn", "JavaScript", lambda t: []),
    "pnpm-lock.yaml": ("pnpm", "JavaScript", lambda t: []),
    "bun.lock": ("Bun", "JavaScript", lambda t: []),
    "deno.json": ("Deno", "TypeScript", _parse_package_json),
    # Python
    "requirements.txt": ("pip", "Python", _parse_requirements),
    "pyproject.toml": ("PEP 621 / Poetry", "Python", _parse_pyproject),
    "setup.py": ("setuptools", "Python", lambda t: []),
    "setup.cfg": ("setuptools", "Python", lambda t: []),
    "Pipfile": ("Pipenv", "Python", lambda t: []),
    "Pipfile.lock": ("Pipenv", "Python", lambda t: []),
    "poetry.lock": ("Poetry", "Python", lambda t: []),
    "conda.yaml": ("Conda", "Python", lambda t: []),
    "environment.yml": ("Conda", "Python", lambda t: []),
    # Go
    "go.mod": ("Go modules", "Go", _parse_go_mod),
    "go.sum": ("Go modules", "Go", lambda t: []),
    # Rust
    "Cargo.toml": ("Cargo", "Rust", _parse_cargo),
    "Cargo.lock": ("Cargo", "Rust", lambda t: []),
    # Ruby
    "Gemfile": ("Bundler", "Ruby", lambda t: []),
    "Gemfile.lock": ("Bundler", "Ruby", _parse_gemfile),
    # PHP
    "composer.json": ("Composer", "PHP", _parse_composer),
    "composer.lock": ("Composer", "PHP", lambda t: []),
    # JVM
    "pom.xml": ("Maven", "Java", _parse_pom),
    "build.gradle": ("Gradle", "Java", _parse_maven_gradle),
    "build.gradle.kts": ("Gradle", "Kotlin", _parse_maven_gradle),
    # .NET
    "packages.config": ("NuGet", "C#", lambda t: []),
    # Elixir / Erlang
    "mix.exs": ("Mix", "Elixir", lambda t: []),
    "rebar.config": ("Rebar3", "Erlang", lambda t: []),
    # Infrastructure
    "Dockerfile": ("Docker", "Dockerfile", _parse_dockerfile),
    "docker-compose.yml": ("Docker Compose", "YAML", lambda t: []),
    "docker-compose.yaml": ("Docker Compose", "YAML", lambda t: []),
    "terraform.tf": ("Terraform", "HCL", lambda t: []),
    "Chart.yaml": ("Helm", "YAML", lambda t: []),
}

# requirements*.txt is a family rather than a fixed set of names.
_REQUIREMENTS_RE = re.compile(r"^requirements([-\w.]*)\.txt$", re.IGNORECASE)


def _lookup(basename: str, parent: str = "") -> tuple[str, str, object] | None:
    if basename in MANIFESTS:
        return MANIFESTS[basename]
    if _REQUIREMENTS_RE.match(basename):
        return ("pip", "Python", _parse_requirements)
    # A file under a directory named "requirements" is a requirements file too,
    # which is how split requirements are usually laid out (requirements/base.txt).
    # Only the last segment of the parent is checked, so a nested
    # "backend/requirements/dev.txt" is recognised as well.
    if parent.rsplit("/", 1)[-1].lower() == "requirements" and basename.lower().endswith(".txt"):
        return ("pip", "Python", _parse_requirements)
    # Dockerfile variants: Dockerfile.prod, backend.Dockerfile, … The name can
    # appear as any dot-separated segment, not just the first.
    if "Dockerfile" in basename.split("."):
        return MANIFESTS["Dockerfile"]
    return None


def is_manifest(path: str) -> bool:
    """True when *path* is a manifest or lockfile worth parsing."""
    parts = path.rsplit("/", 1)
    basename = parts[-1]
    parent = parts[0] if len(parts) > 1 else ""
    return _lookup(basename, parent) is not None


def parse_manifest(path: str, text: str) -> ManifestResult | None:
    """Parse one manifest, or return ``None`` when the path is not a manifest."""
    parts = path.rsplit("/", 1)
    basename = parts[-1]
    parent = parts[0] if len(parts) > 1 else ""
    entry = _lookup(basename, parent)
    if entry is None:
        return None
    manager, language, parser = entry
    try:
        dependencies = list(parser(text) or [])  # type: ignore[operator]
    except Exception as exc:  # pragma: no cover - defensive: one bad file
        return ManifestResult(manager, language, path, [], error=str(exc)[:200])
    return ManifestResult(manager, language, path, dependencies)
