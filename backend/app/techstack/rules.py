"""Technology rule table and the index used to match declared dependencies.

A rule says "a dependency with this name, declared by this kind of package
manager, means the technology X is in use".  The two-tier idea comes from
stack-analyser: a technology is present when **either** a manifest or lockfile
by its name exists **or** a dependency by its name is declared.

Rules live in two places.  :data:`BASE_RULES` is hand-written and covers the
languages a repository is *written in* -- its frameworks, UI libraries, testing
and linting tools.  :data:`EXTENDED_RULES` is generated from stack-analyser's
own rule tree and covers the things a repository *uses*: its databases, hosting
providers, CI, cloud platforms and AI vendors.  Splitting them this way keeps
the hand-maintained part small and reviewable, and makes it obvious which
numbers are exhaustive and which are a curated subset.

A rule's ``managers`` gates it the way stack-analyser's ecosystem label does:
``npm`` there means npm, Yarn, pnpm and Bun alike.  The sentinel ``"*"`` means
"any manager" and is used for tech-to-tech rules, where depending on a database
is evidence of that database regardless of which ecosystem declared it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from app.techstack.models import TechRule, normalise_path

__all__ = [
    "BASE_RULES",
    "COMPONENT_KINDS",
    "EXTENDED_RULES",
    "RULES",
    "build_index",
]


#: Kinds that stand for something a service *connects to* rather than something
#: it is *built with*.  This is the complement of stack-analyser's
#: ``notAComponent`` set, which decides whether a detected technology becomes a
#: node in the service graph: a Postgres dependency or a Vercel config is a
#: separate thing the service talks to, so it becomes a node, while a framework,
#: a test runner, a linter or a CI provider is a property of the service and
#: stays on the service.  Notably CI is *not* a component in their model -- a
#: service does not call its CI provider -- so it is absent here too.
COMPONENT_KINDS = frozenset(
    {
        "AI",
        "Analytics",
        "CDN",
        "CMS",
        "Cloud",
        "Collaboration",
        "Database",
        "Email",
        "Hosting",
        "Messaging",
        "Payments",
        "Queue",
        "Search",
        "Storage",
    }
)


# --- Base rules: what the repository is built with ------------------------ #
# key -> (display name, kind, package managers).  Keys are matched
# case-insensitively against declared dependency names, so "Django" and "django"
# both hit the same rule.
_BASE: dict[str, tuple[str, str, tuple[str, ...]]] = {
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
    "redis": ("Redis", "Database", ("pip", "PEP 621 / Poetry", "setuptools", "npm", "Yarn", "pnpm", "Bun")),
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

BASE_RULES: tuple[TechRule, ...] = (
    *(
        TechRule(key=key, name=display, kind=kind, managers=managers, exact=(key,))
        for key, (display, kind, managers) in _BASE.items()
    ),
    # Not from stack-analyser's tree: it has no rule for the Actions platform
    # itself, only for third-party actions used inside workflows.  A workflow
    # file is the one thing almost every repository has that names its CI, and
    # its own `uses: actions/...` steps are matched by the generated rules.
    TechRule(
        key="github_actions",
        name="GitHub Actions",
        kind="CI/CD",
        files=(".github/workflows",),
    ),
    # Not from stack-analyser's tree either.  Its per-service rules cover
    # `aws_lambda_function` and `aws_dynamodb_table` individually, but the
    # umbrella AWS rule only fires on a declared provider or an SDK client, so a
    # Terraform file with nothing but a bucket would report no cloud at all.  A
    # resource type prefixed `aws_` is not ambiguous, so it is evidence of AWS.
    # This merges into the generated `aws` rule, whose manager set already
    # accepts any manager, so the pattern applies wherever such a name appears.
    TechRule(
        key="aws",
        name="AWS",
        kind="Cloud",
        patterns=(r"^aws_",),
    ),
)

# Imported last: the generated table references ``TechRule`` from above.
from app.techstack.rules_extended import EXTENDED_RULES  # noqa: E402


def _merge(base: TechRule, other: TechRule) -> TechRule:
    """Fold a generated rule into a hand-written one for the same technology.

    Four technologies appear in both tables (``openai``, ``anthropic``,
    ``redis``, ``elasticsearch``).  They agree on the kind, so the hand-written
    label wins -- it is the better capitalised of the two -- and the generated
    matchers are unioned in, since they cover more ecosystems.
    """
    return TechRule(
        key=base.key,
        name=base.name,
        kind=base.kind,
        managers=tuple(sorted(set(base.managers) | set(other.managers))),
        exact=tuple(sorted(set(base.exact) | set(other.exact))),
        patterns=tuple(sorted(set(base.patterns) | set(other.patterns))),
        files=tuple(sorted(set(base.files) | set(other.files))),
    )


def _assemble() -> tuple[TechRule, ...]:
    merged = {rule.key: rule for rule in BASE_RULES}
    for rule in EXTENDED_RULES:
        existing = merged.get(rule.key)
        merged[rule.key] = _merge(existing, rule) if existing else rule
    return tuple(merged.values())


RULES: tuple[TechRule, ...] = _assemble()


@dataclass(frozen=True)
class _PatternRule:
    """A rule paired with its compiled patterns and a cheap literal prefilter.

    An anchored pattern such as ``^aws_s3_`` is preceded by a required prefix
    string, so a dependency can be rejected with a substring test before any
    regular expression runs.  With a few hundred patterns and a few hundred
    dependencies that is the difference between scanning them all and not.
    """

    rule: TechRule
    patterns: tuple[re.Pattern[str], ...] = field(default=())
    prefix: str = ""


@dataclass(frozen=True)
class RuleIndex:
    """Every rule, arranged for the three kinds of match the scan performs.

    ``exact`` is a lookup by literal dependency name, ``patterns`` holds rules
    with a dependency-name regex plus a literal prefilter, and ``files`` splits
    the path evidence into single-segment names -- looked up per path segment,
    which is what lets ``services/api/Jenkinsfile`` match a rule naming
    ``Jenkinsfile`` -- and multi-segment prefixes, checked directly.
    """

    rules: tuple[TechRule, ...]
    exact: dict[str, tuple[TechRule, ...]]
    patterns: tuple[_PatternRule, ...]
    files: dict[str, tuple[TechRule, ...]]
    file_prefixes: tuple[tuple[str, tuple[TechRule, ...]], ...]


def build_index(rules: tuple[TechRule, ...] = RULES) -> RuleIndex:
    """Index rules for matching: literal names, patterns, and file paths."""
    exact: dict[str, list[TechRule]] = {}
    patterns: list[_PatternRule] = []
    files: dict[str, list[TechRule]] = {}
    prefixes: dict[str, list[TechRule]] = {}

    for rule in rules:
        for name in rule.exact:
            exact.setdefault(name.lower(), []).append(rule)

        if rule.patterns:
            compiled = tuple(re.compile(p) for p in rule.patterns)
            # Every pattern must be satisfiable, so the shared literal prefix of
            # the anchored ones is a sound prefilter; unanchored ones get "".
            anchored = [p for p in rule.patterns if p.startswith("^")]
            prefix = ""
            if anchored:
                literals = [p[1:].split("\\")[0].split("[")[0].split("(")[0] for p in anchored]
                prefix = os.path.commonprefix(literals) if literals else ""
            patterns.append(_PatternRule(rule=rule, patterns=compiled, prefix=prefix))

        for path in rule.files:
            path = normalise_path(path)
            target = prefixes if "/" in path else files
            target.setdefault(path, []).append(rule)

    return RuleIndex(
        rules=rules,
        exact={k: tuple(v) for k, v in exact.items()},
        patterns=tuple(patterns),
        files={k: tuple(v) for k, v in files.items()},
        file_prefixes=tuple((k, tuple(v)) for k, v in sorted(prefixes.items())),
    )
