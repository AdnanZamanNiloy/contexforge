"""Language and technology detection for the Dependency & Tech Stack scan.

Two ideas are carried over from stack-analyser:

* a technology is present when **either** a manifest/lockfile by its name
  exists **or** a dependency by its name is declared in some manifest, and
* languages come from a histogram of file extensions.

Its 700-plus rule tree and its 4,300-line copy of GitHub Linguist are not
carried over — a full catalogue is heavy to load and most of it (hosting
providers, SaaS, payment gateways) is out of scope for a report about a
repository's own stack.  What is here is the subset that shows up in real
projects, chosen so the common cases are exact rather than exhaustive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "LANGUAGES",
    "TECH_RULES",
    "detect_technologies",
    "language_histogram",
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


# --- Technology rules ------------------------------------------------------ #
# key -> (display name, kind, matched package-manager names).  A key is matched
# case-insensitively against declared dependency names, so "Django" and "django"
# both hit the same rule.
TECH_RULES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # --- web frameworks ---
    "fastapi": ("FastAPI", "Framework", ("pip", "PEP 621 / Poetry", "setuptools", "Pipenv", "Conda")),
    "django": ("Django", "Framework", ("pip", "PEP 621 / Poetry", "setuptools", "Pipenv", "Conda")),
    "flask": ("Flask", "Framework", ("pip", "PEP 621 / Poetry", "setuptools", "Pipenv", "Conda")),
    "starlette": ("Starlette", "Framework", ("pip", "PEP 621 / Poetry", "setuptools")),
    "sanic": ("Sanic", "Framework", ("pip", "PEP 621 / Poetry", "setuptools")),
    "tornado": ("Tornado", "Framework", ("pip", "PEP 621 / Poetry", "setuptools")),
    "aiohttp": ("aiohttp", "Framework", ("pip", "PEP 621 / Poetry", "setuptools")),
    "express": ("Express", "Framework", ("npm", "Yarn", "pnpm", "Bun")),
    "koa": ("Koa", "Framework", ("npm", "Yarn", "pnpm", "Bun")),
    "fastify": ("Fastify", "Framework", ("npm", "Yarn", "pnpm", "Bun")),
    "nestjs": ("NestJS", "Framework", ("npm", "Yarn", "pnpm", "Bun")),
    "@nestjs/core": ("NestJS", "Framework", ("npm", "Yarn", "pnpm", "Bun")),
    "hapi": ("hapi", "Framework", ("npm", "Yarn", "pnpm", "Bun")),
    "gin-gonic/gin": ("Gin", "Framework", ("Go modules",)),
    "gorm.io/gorm": ("GORM", "Framework", ("Go modules",)),
    "actix-web": ("Actix Web", "Framework", ("Cargo",)),
    "axum": ("Axum", "Framework", ("Cargo",)),
    "rocket": ("Rocket", "Framework", ("Cargo",)),
    "rails": ("Ruby on Rails", "Framework", ("Bundler",)),
    "laravel/framework": ("Laravel", "Framework", ("Composer",)),
    "symfony/framework-bundle": ("Symfony", "Framework", ("Composer",)),
    # --- frontend frameworks / UI ---
    "react": ("React", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "react-dom": ("React", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "next": ("Next.js", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "vue": ("Vue", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "nuxt": ("Nuxt", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "svelte": ("Svelte", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "@sveltejs/kit": ("SvelteKit", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "angular": ("Angular", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "@angular/core": ("Angular", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "solid-js": ("SolidJS", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "tailwindcss": ("Tailwind CSS", "UI framework", ("npm", "Yarn", "pnpm", "Bun")),
    "bootstrap": ("Bootstrap", "UI framework", ("npm", "Yarn", "pnpm", "Bun", "pip")),
    # --- runtimes ---
    "node": ("Node.js", "Runtime", ()),
    "typescript": ("TypeScript", "Language", ("npm", "Yarn", "pnpm", "Bun")),
    "deno": ("Deno", "Runtime", ()),
    "bun": ("Bun", "Runtime", ()),
    # --- data stores / infra clients ---
    "sqlalchemy": ("SQLAlchemy", "Database", ("pip", "PEP 621 / Poetry", "setuptools")),
    "psycopg2": ("psycopg2", "Database", ("pip", "PEP 621 / Poetry", "setuptools")),
    "psycopg": ("psycopg", "Database", ("pip", "PEP 621 / Poetry", "setuptools")),
    "pymongo": ("PyMongo", "Database", ("pip", "PEP 621 / Poetry", "setuptools")),
    "redis": ("Redis (client)", "Database", ("pip", "PEP 621 / Poetry", "setuptools", "npm", "Yarn", "pnpm", "Bun")),
    "elasticsearch": ("Elasticsearch", "Database", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "prisma": ("Prisma", "Database", ("npm", "Yarn", "pnpm", "Bun")),
    "mongoose": ("Mongoose", "Database", ("npm", "Yarn", "pnpm", "Bun")),
    "typeorm": ("TypeORM", "Database", ("npm", "Yarn", "pnpm", "Bun")),
    "diesel": ("Diesel", "Database", ("Cargo",)),
    "gorm": ("GORM", "Database", ("Go modules",)),
    # --- AI / ML ---
    "openai": ("OpenAI", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "anthropic": ("Anthropic", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "langchain": ("LangChain", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "langchain-openai": ("LangChain", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "llama-index": ("LlamaIndex", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "transformers": ("Transformers", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "torch": ("PyTorch", "AI", ("pip", "PEP 621 / Poetry", "Cargo")),
    "tensorflow": ("TensorFlow", "AI", ("pip", "PEP 621 / Poetry", "npm", "Yarn", "pnpm", "Bun")),
    "scikit-learn": ("scikit-learn", "AI", ("pip", "PEP 621 / Poetry", "setuptools")),
    # --- testing ---
    "pytest": ("pytest", "Testing", ("pip", "PEP 621 / Poetry", "setuptools")),
    "unittest2": ("unittest", "Testing", ("pip", "PEP 621 / Poetry")),
    "jest": ("Jest", "Testing", ("npm", "Yarn", "pnpm", "Bun")),
    "vitest": ("Vitest", "Testing", ("npm", "Yarn", "pnpm", "Bun")),
    "mocha": ("Mocha", "Testing", ("npm", "Yarn", "pnpm", "Bun")),
    "cypress": ("Cypress", "Testing", ("npm", "Yarn", "pnpm", "Bun")),
    "@playwright/test": ("Playwright", "Testing", ("npm", "Yarn", "pnpm", "Bun")),
    "playwright": ("Playwright", "Testing", ("npm", "Yarn", "pnpm", "Bun")),
    # --- tooling / quality ---
    "eslint": ("ESLint", "Linting", ("npm", "Yarn", "pnpm", "Bun")),
    "ruff": ("Ruff", "Linting", ("pip", "PEP 621 / Poetry", "setuptools")),
    "black": ("Black", "Linting", ("pip", "PEP 621 / Poetry", "setuptools")),
    "flake8": ("flake8", "Linting", ("pip", "PEP 621 / Poetry", "setuptools")),
    "mypy": ("mypy", "Linting", ("pip", "PEP 621 / Poetry", "setuptools")),
    "prettier": ("Prettier", "Linting", ("npm", "Yarn", "pnpm", "Bun")),
    "webpack": ("webpack", "Build", ("npm", "Yarn", "pnpm", "Bun")),
    "vite": ("Vite", "Build", ("npm", "Yarn", "pnpm", "Bun")),
    "rollup": ("Rollup", "Build", ("npm", "Yarn", "pnpm", "Bun")),
    "esbuild": ("esbuild", "Build", ("npm", "Yarn", "pnpm", "Bun")),
    "babel": ("Babel", "Build", ("npm", "Yarn", "pnpm", "Bun")),
    "@babel/core": ("Babel", "Build", ("npm", "Yarn", "pnpm", "Bun")),
}

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


def language_histogram(paths: list[str]) -> list[dict]:
    """Count files per language across *paths*, ignoring vendored and built trees.

    Vendored and generated directories are skipped outright: without that,
    ``node_modules`` alone would dominate the histogram of any real project.
    """
    counts: dict[tuple[str, str], int] = {}
    for path in paths:
        if _SKIP_DIR.search(path) or _SKIP_FILE.search(path):
            continue
        ext = _extension_of(path)
        if not ext:
            continue
        for language in LANGUAGES:
            if ext in language.extensions:
                key = (language.name, language.kind)
                counts[key] = counts.get(key, 0) + 1
                break

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


def detect_technologies(manifest_results, package_managers: list[str]) -> list[dict]:
    """Match declared dependencies against the rule table.

    A rule fires when a dependency name matches and its declaring package
    manager is one the rule applies to, which keeps a stray ``redis`` in a Go
    project from being reported as a Python client.
    """
    managers = set(package_managers)
    found: dict[str, dict] = {}

    for result in manifest_results:
        for dep in result.dependencies:
            key = dep.name.lower()
            rule = TECH_RULES.get(key)
            if not rule:
                continue
            display, kind, allowed = rule
            if allowed and result.manager not in allowed:
                continue
            entry = found.setdefault(
                display,
                {
                    "name": display,
                    "kind": kind,
                    "version": dep.version,
                    "managers": [],
                    "dependency": dep.name,
                },
            )
            if result.manager not in entry["managers"]:
                entry["managers"].append(result.manager)
            # Prefer a concrete version when one manifest had it and another did not.
            if not entry["version"] and dep.version:
                entry["version"] = dep.version

    # Managers inferred from a lockfile are reported too: a repo can use npm
    # without depending on anything that names it.
    for manager in sorted(managers):
        if manager not in {m for entry in found.values() for m in entry["managers"]}:
            found.setdefault(
                manager,
                {
                    "name": manager,
                    "kind": "Package manager",
                    "version": None,
                    "managers": [manager],
                    "dependency": None,
                },
            )

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
