"""Unit tests for execution data-flow inference."""

from __future__ import annotations

from app.repository_intelligence.data_flow import infer_data_flows


def _nodes_and_edges():
    nodes = [
        {"id": "repo", "label": "repo", "kind": "repo", "path": "/", "deps": 0, "dependents": 0},
        {
            "id": "app/routes/query.py",
            "label": "query.py",
            "kind": "file",
            "path": "app/routes/query.py",
            "deps": 0,
            "dependents": 0,
        },
        {
            "id": "app/services/query_service.py",
            "label": "query_service.py",
            "kind": "file",
            "path": "app/services/query_service.py",
            "deps": 0,
            "dependents": 1,
        },
        {
            "id": "core/storage.py",
            "label": "storage.py",
            "kind": "file",
            "path": "core/storage.py",
            "deps": 0,
            "dependents": 0,
        },
        {"id": "core/llm.py", "label": "llm.py", "kind": "file", "path": "core/llm.py", "deps": 0, "dependents": 0},
    ]
    edges = [
        {
            "source": "app/routes/query.py",
            "target": "app/services/query_service.py",
            "kind": "imports",
            "relationship_source": "ast",
            "confidence": 1.0,
        },
        {
            "source": "app/services/query_service.py",
            "target": "core/storage.py",
            "kind": "imports",
            "relationship_source": "ast",
            "confidence": 1.0,
        },
        {
            "source": "app/services/query_service.py",
            "target": "core/llm.py",
            "kind": "calls",
            "relationship_source": "ast",
            "confidence": 0.7,
        },
    ]
    return nodes, edges


def test_detects_directional_flow_from_route_entry():
    nodes, edges = _nodes_and_edges()
    files = {
        "app/routes/query.py": (
            "from app.services.query_service import QueryService\n"
            '@router.get("/query")\n'
            "def query():\n    return QueryService().search()\n"
        ),
        "app/services/query_service.py": (
            "from core.storage import query_index\n"
            "from core.llm import generate\n"
            "class QueryService:\n"
            "    def search(self, q):\n"
            "        query_index(q)\n        return generate(q)\n"
        ),
        "core/storage.py": "def query_index(q):\n    return q\n",
        "core/llm.py": "def generate(q):\n    return q\n",
    }
    flows = infer_data_flows(nodes, edges, files)
    assert flows
    flow = next(iter(flows.values()))
    assert flow["title"] == "GET /query"
    assert flow["kind"] == "route"
    assert flow["entry"] == "app/routes/query.py"
    assert any(n["entry"] for n in flow["nodes"])
    assert len(flow["edges"]) == 3
    ids = {n["id"] for n in flow["nodes"]}
    assert {"app/routes/query.py", "app/services/query_service.py", "core/storage.py", "core/llm.py"} <= ids
    service = next(n for n in flow["nodes"] if n["id"].endswith("query_service.py"))
    assert service["kind"] == "service"
    assert "core/storage.py" in service["callees"]
    assert "app/routes/query.py" in service["callers"]
    assert "search" in service["functions"]
    # bottlenecks must reflect only real code metrics, never fabricated timings
    for b in flow["bottlenecks"]:
        assert b["latency_ms"] is None
        assert b["dependents"] > 0


def test_marks_external_import_as_dependency():
    nodes, edges = _nodes_and_edges()
    files = {
        "app/routes/query.py": '@router.get("/query")\ndef query():\n    pass\n',
        "app/services/query_service.py": (
            "import requests\nfrom core.storage import query_index\ndef search(q):\n    return requests.get(q)\n"
        ),
        "core/storage.py": "def query_index(q):\n    return q\n",
        "core/llm.py": "def generate(q):\n    return q\n",
    }
    flows = infer_data_flows(nodes, edges, files)
    flow = next(iter(flows.values()))
    service = next(n for n in flow["nodes"] if n["id"].endswith("query_service.py"))
    assert "requests" in service["dependencies"]


def test_no_flows_when_no_execution_signal():
    flows = infer_data_flows(
        [{"id": "README.md", "path": "README.md", "kind": "file", "label": "README.md"}],
        [],
    )
    assert flows == {}
