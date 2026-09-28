"""Dependency & Tech Stack scan.

The parsers are the correctness boundary here: a bad parse means the report
states a wrong version or invents a dependency, so each ecosystem's parser is
exercised against the shapes those files really take, including the partially
indexed ones.
"""

from __future__ import annotations

import json

import pytest

from app.techstack.detectors import language_histogram
from app.techstack.manifests import is_manifest, parse_manifest
from app.techstack.service import TechStackError, TechStackService
from app.techstack.storage import TechStackStore


def _deps(result, name):
    return next((d for d in result.dependencies if d.name == name), None)


# --------------------------------------------------------------------------- #
# Version-spec reduction
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("^1.2.3", "1.2.3"),
        ("~2.0.1", "2.0.1"),
        (">=3.1.0,<4.0.0", "3.1.0"),
        ("==1.0", "1.0"),
        ("1.2.3", "1.2.3"),
        (">=2.0", "2.0"),
        ("*", None),
        ("", None),
        (None, None),
        ("git+https://example.com/x.git", None),
        ("workspace:*", None),
        ("latest", None),
    ],
)
def test_versions_reduce_to_something_readable(spec, expected):
    result = parse_manifest("package.json", json.dumps({"dependencies": {"x": spec}}))
    assert _deps(result, "x").version == expected


# --------------------------------------------------------------------------- #
# Ecosystem parsers
# --------------------------------------------------------------------------- #


def test_package_json_reads_all_four_blocks():
    text = json.dumps(
        {
            "dependencies": {"fastapi": "^0.115.0", "uvicorn": ">=0.30"},
            "devDependencies": {"pytest": "^8.3.0"},
            "peerDependencies": {"react": ">=18"},
            "optionalDependencies": {"fsevents": "~2.3"},
        }
    )
    result = parse_manifest("package.json", text)
    assert result.manager == "npm"
    assert _deps(result, "fastapi").version == "0.115.0"
    assert _deps(result, "fastapi").scope == "runtime"
    assert _deps(result, "pytest").scope == "dev"
    assert _deps(result, "react").scope == "peer"
    assert _deps(result, "fsevents").scope == "optional"


def test_package_json_survives_truncated_json():
    # A partially indexed file must not raise; it just yields nothing.
    result = parse_manifest("package.json", '{"dependencies": {"react": "^18')
    assert result is not None
    assert result.dependencies == []


def test_requirements_txt_skips_directives_comments_and_python():
    text = "\n".join(
        [
            "# a comment",
            "-r other.txt",
            "-e .",
            "",
            "fastapi==0.115.0  # pinned",
            "uvicorn>=0.30,<0.31",
            "requests[security]>=2.32 ; python_version >= '3.9'",
            "python>=3.11",
        ]
    )
    result = parse_manifest("requirements.txt", text)
    assert _deps(result, "fastapi").version == "0.115.0"
    assert _deps(result, "uvicorn").version == "0.30"
    assert _deps(result, "requests").version == "2.32"
    # `python` is the interpreter, not a dependency.
    assert _deps(result, "python") is None


def test_requirements_variants_are_recognised():
    for name in ("requirements.txt", "requirements-dev.txt"):
        assert is_manifest(name), name
    assert parse_manifest("requirements-dev.txt", "ruff==0.6.0").manager == "pip"


def test_split_requirements_under_a_requirements_directory():
    # requirements/base.txt is a common layout; the parent directory is what
    # identifies it, not the basename.
    assert is_manifest("requirements/base.txt")
    result = parse_manifest("backend/requirements/dev.txt", "pytest==8.3.0")
    assert result is not None
    assert _deps(result, "pytest").version == "8.3.0"
    # An unrelated .txt in an unrelated directory is not a manifest.
    assert not is_manifest("docs/notes/base.txt")


def test_pyproject_pep621():
    text = """
[project]
name = "x"
dependencies = ["fastapi>=0.115.0", "httpx==0.27.2"]

[project.optional-dependencies]
dev = ["pytest>=8.3", "ruff"]
"""
    result = parse_manifest("pyproject.toml", text)
    assert _deps(result, "fastapi").version == "0.115.0"
    assert _deps(result, "httpx").version == "0.27.2"
    assert _deps(result, "pytest") is not None


def test_pyproject_poetry_table():
    text = """
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.115.0"
uvicorn = { version = "^0.30", extras = ["standard"] }
django = { version = "5.0" }
"""
    result = parse_manifest("pyproject.toml", text)
    assert _deps(result, "fastapi").version == "0.115.0"
    assert _deps(result, "uvicorn").version == "0.30"
    assert _deps(result, "django").version == "5.0"
    assert _deps(result, "python") is None


def test_go_mod_single_and_block_requires():
    text = """
module example.com/x

go 1.22

require github.com/gin-gonic/gin v1.10.0

require (
    github.com/stretchr/testify v1.9.0 // indirect
    gorm.io/gorm v1.25.10
)
"""
    result = parse_manifest("go.mod", text)
    assert result.manager == "Go modules"
    assert _deps(result, "github.com/gin-gonic/gin").version == "1.10.0"
    assert _deps(result, "gorm.io/gorm").version == "1.25.10"
    assert _deps(result, "github.com/stretchr/testify").version == "1.9.0"


def test_cargo_toml_string_and_table_forms():
    text = """
[package]
name = "x"

[dependencies]
serde = "1.0"
tokio = { version = "1.38", features = ["full"] }

[dev-dependencies]
criterion = "0.5"
"""
    result = parse_manifest("Cargo.toml", text)
    assert _deps(result, "serde").version == "1.0"
    assert _deps(result, "tokio").version == "1.38"
    assert _deps(result, "criterion").version == "0.5"
    assert _deps(result, "criterion").scope == "dev"


def test_gemfile_lock():
    text = """
GEM
  remote: https://rubygems.org/
  specs:
    rails (7.1.3)
    puma (6.4.2)

PLATFORMS
  ruby

DEPENDENCIES
  rails
"""
    result = parse_manifest("Gemfile.lock", text)
    assert _deps(result, "rails").version == "7.1.3"
    assert _deps(result, "puma").version == "6.4.2"


def test_composer_json():
    text = json.dumps(
        {
            "require": {"php": "^8.2", "laravel/framework": "^11.0"},
            "require-dev": {"phpunit/phpunit": "^11"},
        }
    )
    result = parse_manifest("composer.json", text)
    assert _deps(result, "php") is None
    assert _deps(result, "laravel/framework").version == "11.0"
    assert _deps(result, "phpunit/phpunit").scope == "dev"


def test_pom_xml_coordinates():
    text = """
<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
      <version>3.3.0</version>
    </dependency>
  </dependencies>
</project>
"""
    result = parse_manifest("pom.xml", text)
    dep = _deps(result, "org.springframework.boot:spring-boot-starter-web")
    assert dep is not None
    assert dep.version == "3.3.0"


def test_dockerfile_base_image_and_system_packages():
    text = """
FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl ca-certificates
"""
    result = parse_manifest("Dockerfile", text)
    assert _deps(result, "python").version == "3.12-slim"
    assert _deps(result, "curl").scope == "system"


def test_dockerfile_variants_are_matched():
    for name in ("Dockerfile", "Dockerfile.prod", "backend.Dockerfile", "docker/Dockerfile.dev"):
        assert is_manifest(name), name


def test_lockfile_without_dependencies_still_reports_its_manager():
    result = parse_manifest("yarn.lock", "# yarn lockfile v1\n")
    assert result.manager == "Yarn"
    assert result.dependencies == []


def test_non_manifest_is_not_parsed():
    assert not is_manifest("src/main.py")
    assert parse_manifest("src/main.py", "print(1)") is None


# --------------------------------------------------------------------------- #
# Language histogram
# --------------------------------------------------------------------------- #


def test_language_histogram_counts_by_extension():
    paths = ["a.py", "b.py", "c.ts", "d.tsx", "e.js", "f.md", "g.yaml"]
    rows = {row["name"]: row["files"] for row in language_histogram(paths)}
    assert rows["Python"] == 2
    assert rows["TypeScript"] == 2
    assert rows["JavaScript"] == 1
    assert rows["Markdown"] == 1


def test_language_histogram_ignores_vendored_and_built_trees():
    # node_modules alone would otherwise dominate any real project's histogram.
    paths = ["a.py"] + [f"node_modules/pkg{i}/index.js" for i in range(50)] + ["dist/bundle.js", "vendor/c.go"]
    rows = {row["name"]: row["files"] for row in language_histogram(paths)}
    assert rows.get("Python") == 1
    assert "JavaScript" not in rows


def test_language_histogram_prefers_multi_part_suffixes():
    rows = {row["name"]: row["files"] for row in language_histogram(["a.d.ts", "b.ts", "c.ts"])}
    # Both .ts and .d.ts are TypeScript, and must not be double counted as JS.
    assert rows["TypeScript"] == 3


def test_language_histogram_sorts_programming_first():
    paths = ["a.yaml", "b.json", "c.py", "d.md"]
    rows = language_histogram(paths)
    assert rows[0]["name"] == "Python"


def test_language_shares_sum_to_one():
    rows = language_histogram(["a.py", "b.py", "c.ts", "d.md"])
    assert round(sum(row["share"] for row in rows), 4) == 1.0


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class FakeChunk:
    def __init__(self, text, path, repo="acme/widgets"):
        self.text = text
        self.source_id = "repo:acme/widgets"
        self.metadata = {"path": path, "repo": repo, "url": "https://github.com/acme/widgets", "source_type": "github"}


class FakeFaiss:
    def __init__(self, chunks):
        self._chunks = chunks

    async def get_chunks_by_source_id(self, source_id):
        return list(self._chunks)


def _service(tmp_path, chunks):
    return TechStackService(store=TechStackStore(tmp_path / "ts.db"), faiss=FakeFaiss(chunks))


@pytest.fixture
def chunks():
    return [
        FakeChunk(
            '[project]\nname = "widgets"\ndependencies = ["fastapi>=0.115.0"]\n\n'
            '[project.optional-dependencies]\ndev = ["pytest>=8.3"]\n',
            "pyproject.toml",
        ),
        FakeChunk(json.dumps({"dependencies": {"react": "^18.3.0"}}), "frontend/package.json"),
        FakeChunk("print('x')", "app/main.py"),
        FakeChunk("export const a = 1", "frontend/src/a.ts"),
        FakeChunk("x", "node_modules/junk/index.js"),
    ]


@pytest.mark.asyncio
async def test_scan_reports_stack(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["repository"] == "acme/widgets"
    assert result["manifest_count"] == 2
    assert result["dependency_count"] == 3
    langs = {row["name"] for row in result["languages"]}
    assert {"Python", "TypeScript"} <= langs
    frameworks = {row["name"] for row in result["frameworks"]}
    assert "FastAPI" in frameworks
    assert "React" in frameworks
    assert result["summary"]
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_dependencies_are_grouped_by_manager(tmp_path, chunks):
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    managers = {bucket["manager"] for bucket in result["dependencies"]}
    assert "npm" in managers
    assert "PEP 621 / Poetry" in managers
    npm = next(b for b in result["dependencies"] if b["manager"] == "npm")
    assert [d["name"] for d in npm["dependencies"]] == ["react"]


@pytest.mark.asyncio
async def test_scan_is_cached_by_fingerprint(tmp_path, chunks):
    service = _service(tmp_path, chunks)
    first = await service.scan("p1", "repo:acme/widgets")
    second = await service.scan("p1", "repo:acme/widgets")
    assert second["cached"] is True
    assert second["elapsed_ms"] == 0
    assert second["fingerprint"] == first["fingerprint"]


@pytest.mark.asyncio
async def test_new_file_set_invalidates_the_cache(tmp_path, chunks):
    service = _service(tmp_path, chunks)
    await service.scan("p1", "repo:acme/widgets")
    grown = [*chunks, FakeChunk("more", "app/extra.py")]
    result = await _service(tmp_path, grown).scan("p1", "repo:acme/widgets")
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_rescan_bypasses_the_cache(tmp_path, chunks):
    service = _service(tmp_path, chunks)
    await service.scan("p1", "repo:acme/widgets")
    result = await service.scan("p1", "repo:acme/widgets", refresh=True)
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_duplicate_declaration_listed_once(tmp_path):
    # The same package declared in two manifests of one ecosystem is one entry.
    chunks = [
        FakeChunk("fastapi==0.115.0", "requirements.txt"),
        FakeChunk('dependencies = ["fastapi>=0.115.0"]', "pyproject.toml"),
    ]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["dependency_count"] == 1


@pytest.mark.asyncio
async def test_empty_index_raises_a_clear_error(tmp_path):
    with pytest.raises(TechStackError, match="no indexed files"):
        await _service(tmp_path, []).scan("p1", "repo:acme/widgets")


@pytest.mark.asyncio
async def test_repo_without_manifests_reports_languages_only(tmp_path):
    chunks = [FakeChunk("print(1)", "a.py"), FakeChunk("print(2)", "b.py")]
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    assert result["manifest_count"] == 0
    assert result["language_count"] == 1
    assert "No dependency manifests" in result["summary"]


@pytest.mark.asyncio
async def test_summary_is_a_single_clean_sentence(tmp_path, chunks):
    # The tail clause used to be appended with its own full stop, producing
    # "...1 manifest.." — a visible typo in the report header.  The semicolon
    # joined clauses are one sentence; the tail is the second.
    result = await _service(tmp_path, chunks).scan("p1", "repo:acme/widgets")
    summary = result["summary"]
    assert ".." not in summary
    assert summary.endswith(".")
    assert summary.count(".") == 2
    assert "; " in summary


@pytest.mark.asyncio
async def test_get_returns_none_before_a_scan(tmp_path, chunks):
    assert await _service(tmp_path, chunks).get("unknown") is None
