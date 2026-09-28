"""Dependency & Tech Stack scan.

The parsers are the correctness boundary here: a bad parse means the report
states a wrong version or invents a dependency, so each ecosystem's parser is
exercised against the shapes those files really take, including the partially
indexed ones.
"""

from __future__ import annotations

import json

import pytest

from app.techstack.detectors import language_histogram, match_path, match_rules
from app.techstack.graph import MAX_SERVICES, build_graph, flatten_graph
from app.techstack.manifests import (
    Dependency,
    ManifestResult,
    is_manifest,
    parse_manifest,
)
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


# --------------------------------------------------------------------------- #
# Infrastructure manifests
#
# The database, hosting, CI and cloud rules are only reachable if Terraform and
# GitHub Actions are parsed at all: a package.json never mentions aws_s3_bucket,
# and a repository's CI is named by a workflow file rather than a dependency.
# --------------------------------------------------------------------------- #


def test_terraform_resource_types_become_dependencies():
    text = """
    resource "aws_s3_bucket" "logs" { bucket = "x" }
    resource "aws_dynamodb_table" "sessions" {}
    """
    result = parse_manifest("infra/main.tf", text)
    names = {d.name for d in result.dependencies}
    assert {"aws_s3_bucket", "aws_dynamodb_table"} <= names


def test_terraform_module_source_is_read_in_both_layouts():
    # The one-line form is common in examples and in generated code, so the
    # source has to be found even when it does not start its own line.
    one_line = parse_manifest("i/main.tf", 'module "vpc" { source = "terraform-aws-modules/vpc/aws" }')
    assert _deps(one_line, "terraform-aws-modules/vpc/aws") is not None

    multi = parse_manifest(
        "i/main.tf",
        'module "vpc" {\n  source = "terraform-aws-modules/vpc/aws"\n}\n',
    )
    assert _deps(multi, "terraform-aws-modules/vpc/aws") is not None


def test_terraform_data_block_records_its_type_but_not_its_source():
    # A `data` block's type is real evidence of what the project uses, so
    # `data "aws_ami"` records `aws_ami`.  Its `source` attribute names a data
    # set rather than a module, so that is not read as a dependency.
    text = """
    data "aws_ami" "ubuntu" {
      source = "some-ami-id"
    }
    """
    result = parse_manifest("i/main.tf", text)
    names = {d.name for d in result.dependencies}
    assert "aws_ami" in names
    assert "some-ami-id" not in names


def test_terraform_local_module_source_is_not_a_dependency():
    result = parse_manifest("i/main.tf", 'module "local" { source = "./modules/x" }')
    assert result.dependencies == []


def test_terraform_required_providers_yields_the_registry_path():
    # The AWS rule is keyed on the full registry path, which is what a
    # `required_providers` source gives and a bare `provider` block does not.
    text = """
    terraform {
      required_providers {
        aws = {
          source  = "hashicorp/aws"
          version = "~> 5.0"
        }
      }
    }
    """
    result = parse_manifest("i/main.tf", text)
    assert _deps(result, "registry.terraform.io/hashicorp/aws") is not None


def test_terraform_provider_block_also_yields_the_registry_path():
    result = parse_manifest("i/main.tf", 'provider "aws" {\n  region = "us-east-1"\n}\n')
    assert _deps(result, "registry.terraform.io/hashicorp/aws") is not None


def test_workflow_actions_become_dependencies_with_tags():
    text = """
    jobs:
      build:
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
    """
    result = parse_manifest(".github/workflows/ci.yml", text)
    assert _deps(result, "actions/checkout").version == "v4"
    assert _deps(result, "actions/setup-python").version == "v5"


@pytest.mark.parametrize(
    "uses",
    [
        "actions/cache@main",          # a moving branch, not a version
        "actions/cache@0123456789abcdef0123456789abcdef01234567",  # a commit sha
    ],
)
def test_workflow_action_on_a_moving_ref_reports_no_version(uses):
    # Claiming a version for `@main` or a SHA would be inventing a pin the
    # repository does not have.
    result = parse_manifest(".github/workflows/ci.yml", f"      - uses: {uses}\n")
    dep = next(iter(result.dependencies), None)
    assert dep is not None
    assert dep.version is None


def test_workflow_ignores_local_and_docker_uses():
    text = """
      - uses: ./.github/actions/local
      - uses: docker://alpine:3.19
    """
    assert parse_manifest(".github/workflows/ci.yml", text).dependencies == []


def test_workflow_recognised_by_location_not_filename():
    # A workflow is named freely, so only its directory identifies it.  A YAML
    # file anywhere else is not a manifest and must stay out of the scan.
    assert is_manifest(".github/workflows/ci.yml")
    assert is_manifest("deep/nested/.github/workflows/release.yaml")
    assert not is_manifest("README.yml")
    assert not is_manifest(".github/ISSUE.yml")
    assert not is_manifest("config/ci.yml")


def test_terraform_file_recognised_by_extension():
    assert is_manifest("infra/main.tf")
    # State and variable files are generated or local input rather than
    # declarations of what the project uses, and a state file is enormous, so
    # none of them are parsed.
    assert not is_manifest("infra/terraform.tfstate")
    assert not is_manifest("infra/terraform.tfstate.json")
    assert not is_manifest("infra/main.tfvars")
    # A variables file is a declaration like any other, so it is read; it simply
    # contributes nothing, since it holds no resources.
    assert is_manifest("infra/variables.tf")
    assert parse_manifest("infra/variables.tf", 'variable "region" { default = "eu-west-1" }').dependencies == []


# --------------------------------------------------------------------------- #
# File evidence: the half of the two-tier rule that is not a dependency
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".circleci/config.yml", "CircleCI"),
        ("services/api/.circleci/config.yml", "CircleCI"),
        ("circle.yml", "CircleCI"),
        (".gitlab-ci.yml", "Gitlab CI"),
        ("vercel.json", "Vercel"),
        ("apps/web/vercel.json", "Vercel"),
        (".github/workflows/ci.yml", "GitHub Actions"),
        ("apps/web/.github/workflows/ci.yml", "GitHub Actions"),
        (".jenkins/config.xml", "Jenkins"),
    ],
)
def test_config_files_detect_their_technology(path, expected):
    # CI and hosting are declared by a file, not a dependency: nothing in any
    # manifest names CircleCI.
    assert expected in {rule.name for rule in match_path(path)}


def test_dotfile_directory_rules_match_when_nested():
    # `str.lstrip("./")` strips a character set rather than a prefix, which
    # silently turned `.github/workflows` into `github/workflows` and made every
    # nested dotfile directory unmatchable.
    assert "GitHub Actions" in {rule.name for rule in match_path("a/b/.github/workflows/ci.yml")}


def test_an_unrelated_yaml_file_matches_nothing():
    assert match_path("docs/architecture.md") == []
    assert match_path("src/vercel.py") == []


def test_aws_sdk_client_matches_the_aws_cloud_rule():
    keys = {rule.key for rule in match_rules("@aws-sdk/client-s3", "npm")}
    assert "aws" in keys


def test_unknown_dependency_matches_no_rule():
    assert match_rules("left-pad", "npm") == []


def test_manager_gating_still_applies_to_the_new_categories():
    # A Redis client is a Python or JS thing; seeing it declared in a Go module
    # is not evidence of Redis being used.
    assert match_rules("redis", "pip")
    assert match_rules("redis", "Go modules") == []


# --------------------------------------------------------------------------- #
# Service graph
# --------------------------------------------------------------------------- #


def _monorepo():
    manifests = [
        ManifestResult(
            "npm", "JavaScript", "package.json", [Dependency("next", "14"), Dependency("@acme/api", "1.0")]
        ),
        ManifestResult("npm", "JavaScript", "apps/web/package.json", [Dependency("next", "14")]),
        ManifestResult("npm", "JavaScript", "packages/api/package.json", [Dependency("pg", "8.11")]),
        ManifestResult(
            "pip", "Python", "services/ml/requirements.txt", [Dependency("psycopg2", "2.9")]
        ),
    ]
    paths = [
        "package.json",
        "apps/web/package.json",
        "apps/web/src/index.tsx",
        "apps/web/vercel.json",
        "apps/web/.github/workflows/ci.yml",
        "packages/api/package.json",
        "packages/api/src/main.ts",
        "services/ml/requirements.txt",
        "services/ml/train.py",
    ]
    return build_graph(manifests, paths, "acme/monorepo")


def test_graph_finds_every_service():
    graph = _monorepo()
    assert graph["service_count"] == 4
    assert graph["monorepo"] is True
    assert {s["name"] for s in graph["services"]} == {"acme/monorepo", "web", "api", "ml"}


def test_graph_nests_a_service_under_its_parent():
    # The root package.json makes the repository itself a service, and apps/web
    # is a folder inside it, so it becomes a child rather than a sibling.
    graph = _monorepo()
    root = next(s for s in graph["services"] if s["path"] == [])
    assert [c["name"] for c in root["childs"] if c["node_type"] == "service"] == ["web", "api", "ml"]


def test_graph_draws_an_edge_from_a_service_to_its_database():
    graph = _monorepo()
    api = next(s for s in graph["services"] if s["name"] == "api")
    assert [e["target"] for e in api["edges"]] == [".#postgresql"]
    # And the database is a component node, not a property of the service.
    assert api["techs"][0]["name"] == "Postgres"
    assert [c["node_type"] for c in api["childs"]] == ["component"]


def test_graph_shares_one_component_between_services():
    # Two services declaring the same client reach one Postgres node, which is
    # what makes the graph a graph rather than a list.
    manifests = [
        ManifestResult("npm", "JavaScript", "a/package.json", [Dependency("pg", "8")]),
        ManifestResult("pip", "Python", "b/requirements.txt", [Dependency("pg", "8")]),
    ]
    graph = build_graph(manifests, ["a/package.json", "b/requirements.txt"], "acme/x")
    assert graph["component_count"] == 1
    targets = {e["target"] for s in graph["services"] for e in s["edges"]}
    assert targets == {".#postgresql"}
    # Only the first service nests it; the other reaches it by edge.
    nested = [s for s in graph["services"] if any(c["node_type"] == "component" for c in s["childs"])]
    assert len(nested) == 1


def test_graph_records_hosting_as_a_containing_component():
    # A hosting provider contains the service rather than being called by it,
    # so it sets `in_component` and draws no edge.
    graph = _monorepo()
    web = next(s for s in graph["services"] if s["name"] == "web")
    assert web["in_component"] == ".#vercel"
    assert web["edges"] == []


def test_graph_does_not_turn_config_files_into_services():
    # `infra/main.tf` and `.github/workflows` describe the folder they sit in;
    # neither is a deployable service of its own.
    manifests = [
        ManifestResult("npm", "JavaScript", "package.json", [Dependency("next", "14")]),
        ManifestResult("Terraform", "HCL", "infra/main.tf", [Dependency("aws_s3_bucket", None)]),
        ManifestResult("GitHub Actions", "YAML", ".github/workflows/ci.yml", [Dependency("actions/checkout", "v4")]),
    ]
    graph = build_graph(manifests, ["package.json", "infra/main.tf", ".github/workflows/ci.yml"], "acme/x")
    assert {s["name"] for s in graph["services"]} == {"acme/x"}
    techs = {t["name"] for t in graph["services"][0]["techs"]}
    assert {"AWS", "GitHub Actions"} <= techs


def test_graph_gives_a_nested_service_its_own_subdirectory_evidence():
    # The workflow and vercel.json live *inside* apps/web rather than beside its
    # manifest, so a service that only looked at its own folder would see nothing.
    graph = _monorepo()
    web = next(s for s in graph["services"] if s["name"] == "web")
    assert {"Vercel", "GitHub Actions"} <= {t["name"] for t in web["techs"]}


def test_graph_keeps_a_nested_services_files_out_of_its_parent():
    manifests = [
        ManifestResult("npm", "JavaScript", "package.json", [Dependency("next", "14")]),
        ManifestResult("npm", "JavaScript", "apps/web/package.json", [Dependency("next", "14")]),
    ]
    graph = build_graph(manifests, ["package.json", "apps/web/package.json"], "acme/x")
    root = next(s for s in graph["services"] if s["path"] == [])
    # The root's manifest list is its own; the child's stays with the child.
    assert root["manifests"] == ["package.json"]
    web = next(s for s in graph["services"] if s["name"] == "web")
    assert web["manifests"] == ["apps/web/package.json"]


def test_ci_is_not_a_component_node():
    # stack-analyser's `notAComponent` set includes `ci`: a service does not
    # call its CI provider, so CI is a property of the service.
    graph = _monorepo()
    web = next(s for s in graph["services"] if s["name"] == "web")
    assert "GitHub Actions" in {t["name"] for t in web["techs"]}
    assert all(c["node_type"] != "component" or c["tech"] != "github_actions" for c in web["childs"])


def test_graph_node_ids_are_stable_across_builds():
    # Ids come from the folder path, so a rescan of an unchanged repository
    # produces the same ids and a cached graph stays comparable.
    assert _monorepo()["edges"] == _monorepo()["edges"]


def test_graph_handles_a_repository_with_no_manifests():
    graph = build_graph([], ["README.md", "main.py"], "acme/docs")
    assert graph["services"] == []
    assert graph["service_count"] == 0
    assert graph["monorepo"] is False


def test_graph_reports_a_single_service_repository_as_not_a_monorepo():
    graph = build_graph(
        [ManifestResult("pip", "Python", "requirements.txt", [Dependency("django", "5.2")])],
        ["requirements.txt", "app.py"],
        "acme/app",
    )
    assert graph["service_count"] == 1
    assert graph["monorepo"] is False


def test_graph_sibling_edge_ignores_generic_dependency_names():
    # Matching a dependency named "utils" against a sibling folder called "utils"
    # is the false positive stack-analyser warns about, so generic names are
    # not treated as references.
    manifests = [
        ManifestResult("npm", "JavaScript", "apps/web/package.json", [Dependency("utils", "1.0")]),
        ManifestResult("npm", "JavaScript", "packages/utils/package.json", []),
    ]
    graph = build_graph(
        manifests, ["apps/web/package.json", "packages/utils/package.json"], "acme/x"
    )
    assert graph["edges"] == []


def test_graph_sibling_edge_links_a_named_service():
    manifests = [
        ManifestResult("npm", "JavaScript", "apps/web/package.json", [Dependency("@acme/billing", "1.0")]),
        ManifestResult("npm", "JavaScript", "services/billing/package.json", []),
    ]
    graph = build_graph(
        manifests, ["apps/web/package.json", "services/billing/package.json"], "acme/x"
    )
    assert [e["from"] for e in graph["edges"]] == ["apps/web"]
    assert [e["to"] for e in graph["edges"]] == ["services/billing"]


def test_graph_ids_survive_a_json_round_trip(tmp_path):
    # The graph is cached as JSON, and edges reference nodes by id, so the
    # references have to still resolve after a reload.
    graph = _monorepo()
    reloaded = json.loads(json.dumps(graph))
    ids = {c["id"] for c in reloaded["components"]}
    for edge in reloaded["edges"]:
        assert (edge["from"] and edge["to"] in ids) or edge["to"] in {s["id"] for s in reloaded["services"]}


def test_flatten_graph_walks_the_tree_depth_first():
    rows = flatten_graph(_monorepo())
    assert rows[0]["depth"] == 0
    assert any(r["depth"] == 1 for r in rows)
    # root service -> nested service -> the component it connects to.
    assert max(r["depth"] for r in rows) == 2
    assert rows[-1]["node_type"] == "component"


def test_graph_reports_the_real_service_total_when_capped():
    # A capped tree that reported only the capped number would understate a
    # large monorepo, so the real total is carried alongside it.
    manifests = [
        ManifestResult("npm", "JavaScript", f"pkg{index}/package.json", [])
        for index in range(MAX_SERVICES + 25)
    ]
    graph = build_graph(manifests, [f"pkg{index}/package.json" for index in range(MAX_SERVICES + 25)], "acme/x")
    assert graph["service_count"] == MAX_SERVICES
    assert graph["service_total"] == MAX_SERVICES + 25
    assert graph["service_truncated"] is True
    assert graph["monorepo"] is True


def test_graph_is_not_marked_truncated_when_it_fits():
    graph = _monorepo()
    assert graph["service_truncated"] is False
    assert graph["service_total"] == graph["service_count"]
