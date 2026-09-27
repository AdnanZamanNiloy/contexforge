"""Shared fixtures for the test suites."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.repository_intelligence.git import GitRepository

# Every on-disk location a test could write to, mapped to a sensible filename
# under ``tmp_path``.  Redirected wholesale so a test can never reach the
# developer's real databases even if a dependency override is mis-keyed or a
# store is constructed directly.
_ISOLATED_PATHS = {
    "FAISS_INDEX_PATH": "vector_store/index.faiss",
    "BM25_DB_PATH": "bm25/bm25.db",
    "CACHE_PATH": "cache/embeddings.json",
    "UPLOAD_DIR": "uploads",
    "REPO_ANALYSIS_DIR": "repo_analysis",
    "MINDMAP_DIR": "mindmaps",
    "MODEL_HUB_DB_PATH": "model_hub/model_hub.db",
    "PROJECTS_DB_PATH": "projects/projects.db",
}


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path, monkeypatch):
    """Point all persistent storage at ``tmp_path`` for every test.

    Backstop for test isolation: the ``hub_models`` table in the developer's
    live database was previously polluted by integration tests because their
    ``app.dependency_overrides`` entry was keyed on a wrapper function instead of
    the real dependency, so the route silently used the production store.
    """
    from app.config.settings import settings

    for attr, relative in _ISOLATED_PATHS.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(settings, attr, target)

    # The dependency factories are lru_cached singletons, so any store already
    # built (or cached by an earlier test) still points at the real path.
    import app.dependencies as deps

    for name in dir(deps):
        obj = getattr(deps, name)
        if hasattr(obj, "cache_clear"):
            obj.cache_clear()

    yield

    for name in dir(deps):
        obj = getattr(deps, name)
        if hasattr(obj, "cache_clear"):
            obj.cache_clear()


def _init_repo(path: Path, files: dict[str, str], author: str = "daniel-w") -> Path:
    """Create a git repository at *path* with the given files committed."""
    import subprocess

    def run(*args: str) -> None:
        subprocess.run(args, cwd=str(path), check=True, capture_output=True)

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    run("git", "config", "user.email", f"{author}@example.com")
    run("git", "config", "user.name", author)
    for rel, content in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "initial commit")
    return path


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A small multi-directory Python repository with a test file."""
    return _init_repo(
        tmp_path / "sample",
        {
            "app/app.py": "def main():\n    return 'hi'\n",
            "app/services/query_service.py": (
                "from core.retrieval.hybrid_retriever import fuse\n"
                "class QueryService:\n"
                "    def query(self):\n"
                "        return fuse()\n"
            ),
            "core/__init__.py": "",
            "core/retrieval/hybrid_retriever.py": "def fuse():\n    return 1\n",
            "tests/test_query.py": (
                "from app.services.query_service import QueryService\n"
                "def test_query():\n"
                "    assert QueryService().query() == 1\n"
            ),
        },
    )


@pytest.fixture
def single_commit_repo(tmp_path: Path) -> Path:
    """A repository with exactly one commit for history assertions."""
    return _init_repo(
        tmp_path / "single",
        {
            "core/foo.py": "def bar():\n    return 42\n",
        },
    )


@pytest.fixture
def flow_repo(tmp_path: Path) -> Path:
    """A repository with a real HTTP route entry that drives a call chain.

    Used to assert the Data Flow view detects a directional, graph-shaped
    execution flow (route -> service -> storage/llm) with real node metadata.
    """
    return _init_repo(
        tmp_path / "flowrepo",
        {
            "app/routes/query.py": (
                "from app.services.query_service import QueryService\n"
                "router = Router()\n"
                "@router.get('/query')\n"
                "def query(name: str):\n"
                "    return QueryService().search(name)\n"
            ),
            "app/__init__.py": "",
            "app/services/__init__.py": "",
            "app/services/query_service.py": (
                "import requests\n"
                "from core.storage import query_index\n"
                "from core.llm import generate\n"
                "class QueryService:\n"
                "    def search(self, q):\n"
                "        query_index(q)\n"
                "        return generate(q)\n"
            ),
            "core/__init__.py": "",
            "core/storage.py": "def query_index(q: str):\n    return q\n",
            "core/llm.py": "def generate(q: str):\n    return q\n",
        },
    )


@pytest.fixture
def git_repo(sample_repo: Path) -> GitRepository:
    """A GitRepository pointing at a local checkout (no clone needed)."""
    return GitRepository(str(sample_repo))


@pytest.fixture
def analysis_dir(tmp_path: Path, monkeypatch) -> Path:
    """Point Repository Intelligence storage/clone dir at a temp directory."""
    from app.config.settings import settings

    target = tmp_path / "repo_analysis"
    monkeypatch.setattr(settings, "REPO_ANALYSIS_DIR", target)
    return target
