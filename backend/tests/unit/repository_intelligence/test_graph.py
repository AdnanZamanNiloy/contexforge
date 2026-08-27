"""Unit tests for the code-graph builder."""

from __future__ import annotations

from pathlib import Path

from app.repository_intelligence import graph


class TestDiscoverFiles:
    def test_skips_venv_node_modules_and_binary(self, tmp_path: Path):
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "x.py").write_text("x", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "y.js").write_text("x", encoding="utf-8")
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "ok.py").write_text("ok", encoding="utf-8")
        (tmp_path / "app" / "bad.png").write_bytes(b"\x00")
        (tmp_path / "app" / "package-lock.json").write_text("{}", encoding="utf-8")

        found = graph.discover_files(tmp_path)
        rels = [str(p.relative_to(tmp_path)) for p in found]
        assert rels == ["app/ok.py"]

    def test_respects_max_files(self, tmp_path: Path, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "REPO_MAX_FILES", 2)
        for i in range(5):
            (tmp_path / f"src_{i}.py").write_text("x", encoding="utf-8")
        found = graph.discover_files(tmp_path)
        assert len(found) == 2

    def test_not_skipped_when_root_named_like_skip_dir(self, tmp_path: Path):
        # Reproduces the bug where files under data/repo_analysis/<repo>/...
        # were all rejected because the *absolute* path contained "data",
        # which used to be in _SKIP_DIRS. Skip matching must be relative.
        root = tmp_path / "data" / "repo_analysis" / "myrepo"
        (root / "src").mkdir(parents=True)
        (root / "src" / "app.py").write_text("def a(): pass", encoding="utf-8")
        found = graph.discover_files(root)
        rels = [str(p.relative_to(root)) for p in found]
        assert rels == ["src/app.py"]


class TestBuildGraph:
    def test_hierarchy_and_imports(self, sample_repo: Path):
        result = graph.build_graph(sample_repo)
        ids = [n["id"] for n in result["nodes"]]
        assert "repo" in ids
        assert "app/services/query_service.py" in ids
        assert "core/retrieval/hybrid_retriever.py" in ids
        assert result["language"] == "Python"

        contains = [e for e in result["edges"] if e["kind"] == "contains"]
        imports = [e for e in result["edges"] if e["kind"] == "imports"]
        assert any(e["source"] == "app" for e in contains)
        assert any(
            e["source"] == "app/services/query_service.py" and e["target"] == "core/retrieval/hybrid_retriever.py"
            for e in imports
        )
        assert all(e["relationship_source"] == "ast" for e in imports)

    def test_aggregates_files_and_loc_up_tree(self, sample_repo: Path):
        result = graph.build_graph(sample_repo)
        by_id = {n["id"]: n for n in result["nodes"]}
        app = by_id["app"]
        assert app["files"] >= 2
        assert app["loc"] >= 6

    def test_resolves_namespace_over_longest_prefix(self, sample_repo: Path):
        result = graph.build_graph(sample_repo)
        ns = {n["path"][:-3].replace("/", "."): n["id"] for n in result["nodes"] if n["kind"] == "file"}
        target = graph.resolve_import_target("core.retrieval.hybrid_retriever", ns)
        assert target == "core/retrieval/hybrid_retriever.py"
