"""Unit tests for dependency / edge analysis."""

from __future__ import annotations

from app.repository_intelligence import dependencies


class TestDegree:
    def test_enrich_counts_non_containment_edges(self):
        nodes = [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ]
        edges = [
            {"source": "a", "target": "b", "kind": "imports"},
            {"source": "b", "target": "c", "kind": "calls"},
            {"source": "repo", "target": "a", "kind": "contains"},
        ]
        out = dependencies.enrich_nodes_with_degree(nodes, edges)
        by_id = {n["id"]: n for n in out}
        assert by_id["a"]["deps"] == 1
        assert by_id["b"]["dependents"] == 1
        assert by_id["b"]["deps"] == 1


class TestCalls:
    def test_derive_calls_from_qualified_usage(self):
        nodes = [
            {"id": "consumer", "kind": "file", "path": "consumer.py"},
            {"id": "lib", "kind": "file", "path": "lib.py"},
        ]
        files_by_rel = {
            "consumer.py": "import lib\nlib.run()\n",
            "lib.py": "def run():\n    return 1\n",
        }
        ns = {"lib": "lib"}
        edges = dependencies.derive_calls(nodes, [], ns, files_by_rel)
        assert any(e["kind"] == "calls" for e in edges)
        assert all(e["relationship_source"] == "ast" for e in edges)
        assert all(e["confidence"] < 1.0 for e in edges)


class TestSubgraph:
    def test_hops_are_bounded_and_exclude_contains(self):
        nodes = [{"id": str(i)} for i in range(6)]
        edges = [
            {"source": "0", "target": "1", "kind": "imports"},
            {"source": "1", "target": "2", "kind": "imports"},
            {"source": "2", "target": "3", "kind": "imports"},
            {"source": "repo", "target": "0", "kind": "contains"},
        ]
        result = dependencies.build_dependency_subgraph(nodes, edges, "0", depth=1)
        ids = {n["id"] for n in result["nodes"]}
        assert ids == {"0", "1"}
        assert all(e["kind"] != "contains" for e in result["edges"])


class TestRankedModules:
    def test_ranks_by_dependency_weight(self):
        nodes = [
            {"kind": "file", "path": "high.py", "deps": 10, "dependents": 10},
            {"kind": "file", "path": "low.py", "deps": 1, "dependents": 0},
        ]
        ranked = dependencies.ranked_modules(nodes)
        assert ranked[0]["name"] == "high.py"
        assert ranked[0]["value"] > ranked[1]["value"]
