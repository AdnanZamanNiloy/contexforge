"""Shared fixtures for the test suites."""

from __future__ import annotations

import pytest

# Every on-disk location a test could write to, mapped to a sensible filename
# under ``tmp_path``.  Redirected wholesale so a test can never reach the
# developer's real databases even if a dependency override is mis-keyed or a
# store is constructed directly.
_ISOLATED_PATHS = {
    "FAISS_INDEX_PATH": "vector_store/index.faiss",
    "BM25_DB_PATH": "bm25/bm25.db",
    "CACHE_PATH": "cache/embeddings.json",
    "UPLOAD_DIR": "uploads",
    "MINDMAP_DIR": "mindmaps",
    "ARCHITECTURE_DB_PATH": "architecture/architecture.db",
    "TECH_STACK_DB_PATH": "tech_stack/tech_stack.db",
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
