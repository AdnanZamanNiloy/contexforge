"""Architecture Diagram generation pipeline.

No live provider: the LLM is stubbed, so these assert the correctness boundary
that matters — that node paths are checked against the real repository and that
a path fault is repaired rather than costing a second model call.
"""

from __future__ import annotations

import json
import re

import pytest

from app.architecture.graph import (
    ArchitectureGraph,
    GraphEdge,
    GraphGroup,
    GraphNode,
    compile_mermaid,
    escape_mermaid_text,
    parse_graph,
    strip_unknown_paths,
    validate_graph,
)
from app.architecture.service import ArchitectureError, ArchitectureService
from app.architecture.storage import ArchitectureStore


class FakeChunk:
    def __init__(self, text: str, path: str, repo: str = "acme/widgets", url: str | None = None) -> None:
        self.text = text
        self.source_id = "repo:acme/widgets"
        self.metadata = {
            "path": path,
            "repo": repo,
            "url": url or "https://github.com/acme/widgets",
            "source_type": "github",
        }


class FakeFaiss:
    def __init__(self, chunks: list[FakeChunk]) -> None:
        self._chunks = chunks

    async def get_chunks_by_source_id(self, source_id: str | None) -> list[FakeChunk]:
        return list(self._chunks)


class ScriptedLLM:
    """Returns queued replies, recording how many calls were actually made."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str | None]] = []

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.calls.append((prompt, system_prompt))
        return self._replies.pop(0) if self._replies else "{}"


def _payload(explanation: str = "A tiny service.", paths: dict[str, str] | None = None) -> str:
    paths = paths or {"n1": "app/main.py", "n2": "app/db.py"}
    return json.dumps(
        {
            "explanation": explanation,
            "graph": {
                "groups": [{"id": "g1", "label": "Core"}],
                "nodes": [
                    {"id": "n1", "label": "API", "group": "g1", "path": paths["n1"], "shape": "box"},
                    {"id": "n2", "label": "Store", "group": "g1", "path": paths["n2"], "shape": "database"},
                ],
                "edges": [{"from": "n1", "to": "n2", "label": "writes"}],
            },
        }
    )


@pytest.fixture
def chunks() -> list[FakeChunk]:
    return [
        FakeChunk("def main(): ...", "app/main.py"),
        FakeChunk("class Store: ...", "app/db.py"),
        FakeChunk("SQL tables", "app/schema.sql"),
        FakeChunk("# Widgets", "README.md"),
        FakeChunk("junk", "node_modules/left-pad/index.js"),
    ]


# --------------------------------------------------------------------------- #
# Graph parsing / validation
# --------------------------------------------------------------------------- #


def test_parse_graph_reads_fenced_json():
    raw = "```json\n" + _payload() + "\n```"
    graph, issues = parse_graph(raw)
    assert issues == []
    assert graph is not None
    assert [n.id for n in graph.nodes] == ["n1", "n2"]
    assert graph.edges[0].label == "writes"


def test_parse_graph_drops_edges_to_unknown_nodes():
    raw = json.dumps(
        {
            "explanation": "x",
            "graph": {
                "groups": [],
                "nodes": [{"id": "n1", "label": "A", "path": "a.py"}],
                "edges": [{"from": "n1", "to": "ghost"}],
            },
        }
    )
    graph, _issues = parse_graph(raw)
    assert graph is not None
    assert graph.edges == []


def test_parse_graph_rejects_unreadable_output():
    graph, issues = parse_graph("not json at all")
    assert graph is None
    assert issues and issues[0].category == "invalid_json"


def test_validate_flags_paths_absent_from_the_tree():
    graph, _ = parse_graph(_payload(paths={"n1": "app/main.py", "n2": "app/ghost.py"}))
    assert graph is not None
    result = validate_graph(graph, {"app/main.py", "app/db.py"})
    assert not result.valid
    assert result.only_bad_paths()


def test_only_bad_paths_is_false_when_structure_is_broken():
    graph, _ = parse_graph(_payload())
    assert graph is not None
    graph.nodes[0] = GraphNode(id="n1", label="API", group="ghost-group", path="app/main.py")
    result = validate_graph(graph, {"app/main.py", "app/db.py"})
    assert not result.valid
    assert not result.only_bad_paths()


# --------------------------------------------------------------------------- #
# Mermaid compilation
# --------------------------------------------------------------------------- #


def test_compile_emits_flowchart_groups_edges_and_links():
    graph, _ = parse_graph(_payload())
    assert graph is not None
    mermaid = compile_mermaid(graph, owner="acme", repo="widgets", branch="main")
    assert mermaid.startswith("flowchart TD")
    assert 'subgraph g_g1["Core"]' in mermaid
    assert 'n_n1 -->|"writes"| n_n2' in mermaid
    assert "https://github.com/acme/widgets/blob/main/app/main.py" in mermaid
    # A database node uses the store shape, not a plain box.
    assert 'n_n2[("Store")]' in mermaid


def test_compile_is_deterministic():
    graph, _ = parse_graph(_payload())
    assert graph is not None
    first = compile_mermaid(graph, owner="a", repo="b", branch="main")
    second = compile_mermaid(graph, owner="a", repo="b", branch="main")
    assert first == second


def test_compile_skips_links_for_nodes_without_a_path():
    graph = ArchitectureGraph(groups=[], nodes=[GraphNode(id="n1", label="User")], edges=[])
    mermaid = compile_mermaid(graph, owner="a", repo="b", branch="main")
    assert "click" not in mermaid


def test_escape_neutralises_mermaid_metacharacters():
    escaped = escape_mermaid_text('a "b" [c] (d) | e # f `g`')
    # Entity codes legitimately contain '#' and ';', so decode them away before
    # asserting that no *bare* metacharacter survived.
    decoded = re.sub(r"&#?\w+;", "", escaped)
    for char in '"`[]()|#\\<>{}':
        assert char not in decoded
    assert escape_mermaid_text("") == "Unnamed"


def test_escape_folds_away_line_breaks():
    # A raw newline inside a quoted label would end the declaration and let the
    # rest of the text be parsed as Mermaid source.
    escaped = escape_mermaid_text('first\nclick evil "x"')
    assert "\n" not in escaped
    assert "click" in escaped


def test_label_cannot_break_out_of_its_quotes():
    graph = ArchitectureGraph(groups=[], nodes=[GraphNode(id="n1", label='x"]:::evil\nclick a "b"')], edges=[])
    mermaid = compile_mermaid(graph, owner="a", repo="b", branch="main")
    # The declaration stays on one line and the quotes/brackets that would have
    # ended it are entities, so the payload cannot escape the label.
    declaration = next(line for line in mermaid.splitlines() if line.startswith("n_n1["))
    assert "&#93;" in declaration
    assert "&quot;" in declaration
    assert "\nclick" not in mermaid
    assert mermaid.count("n_n1[") == 1


def test_strip_unknown_paths_keeps_the_graph():
    graph, _ = parse_graph(_payload(paths={"n1": "app/main.py", "n2": "app/nope.py"}))
    assert graph is not None
    stripped, count = strip_unknown_paths(graph, {"app/main.py"})
    assert count == 1
    assert stripped.nodes[1].path is None
    assert len(stripped.nodes) == 2


# --------------------------------------------------------------------------- #
# Service pipeline
# --------------------------------------------------------------------------- #


def _service(tmp_path, chunks, replies) -> tuple[ArchitectureService, ScriptedLLM]:
    llm = ScriptedLLM(replies)
    store = ArchitectureStore(tmp_path / "arch.db")
    return ArchitectureService(store=store, faiss=FakeFaiss(chunks), llm=llm), llm


@pytest.mark.asyncio
async def test_explanation_is_the_prose_not_the_json(tmp_path, chunks):
    # A model that returns *only* the JSON leaves no leading prose, so a naive
    # "text before the first brace" extraction would put the whole object in
    # front of the diagram.
    service, _ = _service(tmp_path, chunks, [_payload("A short readable summary.")])
    record = await service.generate("p1", "repo:acme/widgets")
    assert record["explanation"] == "A short readable summary."
    assert "flowchart" not in record["explanation"]


@pytest.mark.asyncio
async def test_explanation_falls_back_to_prose_before_the_json(tmp_path, chunks):
    raw = "Here is the map.\n\n" + _payload("Summary text.")
    service, _ = _service(tmp_path, chunks, [raw])
    record = await service.generate("p1", "repo:acme/widgets")
    assert record["explanation"] == "Summary text."


@pytest.mark.asyncio
async def test_generate_produces_mermaid_and_caches(tmp_path, chunks):
    service, llm = _service(tmp_path, chunks, [_payload()])
    first = await service.generate("p1", "repo:acme/widgets")
    assert first["node_count"] == 2
    assert first["cached"] is False
    assert first["mermaid"].startswith("flowchart TD")
    assert len(llm.calls) == 1

    second = await service.generate("p1", "repo:acme/widgets")
    assert second["cached"] is True
    assert second["mermaid"] == first["mermaid"]
    # The cache is what kept the second call free.
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_generate_refresh_bypasses_the_cache(tmp_path, chunks):
    service, llm = _service(tmp_path, chunks, [_payload(), _payload()])
    await service.generate("p1", "repo:acme/widgets")
    await service.generate("p1", "repo:acme/widgets", refresh=True)
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_fingerprint_changes_when_the_file_set_changes(tmp_path, chunks):
    service, _ = _service(tmp_path, chunks, [_payload(), _payload("A different summary.")])
    await service.generate("p1", "repo:acme/widgets")

    grown = [*chunks, FakeChunk("more", "app/extra.py")]
    service2, _ = _service(tmp_path, grown, [_payload("A different summary.")])
    record = await service2.generate("p1", "repo:acme/widgets")
    assert record["cached"] is False
    assert record["explanation"] == "A different summary."


@pytest.mark.asyncio
async def test_bad_path_is_repaired_without_a_second_model_call(tmp_path, chunks):
    bad = _payload(paths={"n1": "app/main.py", "n2": "app/imagined.py"})
    service, llm = _service(tmp_path, chunks, [bad])
    record = await service.generate("p1", "repo:acme/widgets")
    assert record["truncated_paths"] == 1
    assert len(llm.calls) == 1
    # The surviving real path still links; the invented one is simply gone.
    assert "app/main.py" in record["mermaid"]
    assert "imagined" not in record["mermaid"]


@pytest.mark.asyncio
async def test_unreadable_output_costs_exactly_one_repair(tmp_path, chunks):
    service, llm = _service(tmp_path, chunks, ["garbage", _payload()])
    record = await service.generate("p1", "repo:acme/widgets")
    assert record["node_count"] == 2
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_unreadable_output_after_repair_raises(tmp_path, chunks):
    service, llm = _service(tmp_path, chunks, ["garbage", "still garbage"])
    with pytest.raises(ArchitectureError):
        await service.generate("p1", "repo:acme/widgets")
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_empty_index_raises_a_clear_error(tmp_path):
    service, llm = _service(tmp_path, [], [_payload()])
    with pytest.raises(ArchitectureError, match="no indexed files"):
        await service.generate("p1", "repo:acme/widgets")
    assert llm.calls == []


@pytest.mark.asyncio
async def test_prompt_carries_the_tree_readme_and_bounded_files(tmp_path, chunks):
    service, llm = _service(tmp_path, chunks, [_payload()])
    await service.generate("p1", "repo:acme/widgets")
    prompt = llm.calls[0][0]
    assert "<file_tree>" in prompt
    assert "app/main.py" in prompt
    # The README is a real path, so it is in the tree, and its prose is
    # additionally surfaced in its own block.
    assert "<readme>" in prompt
    assert "# Widgets" in prompt
    assert "node_modules" not in prompt  # noise never reaches the model
    # The ceiling that keeps the call inside its token budget.
    assert len(prompt) <= 26_000


@pytest.mark.asyncio
async def test_get_returns_none_before_anything_is_generated(tmp_path, chunks):
    service, _ = _service(tmp_path, chunks, [_payload()])
    assert await service.get("unknown-project") is None


def test_unused_group_members_still_compile():
    graph = ArchitectureGraph(
        groups=[GraphGroup(id="g1", label="Empty"), GraphGroup(id="g2", label="Used")],
        nodes=[GraphNode(id="n1", label="A", group="g2")],
        edges=[GraphEdge(source="n1", target="n1")],
    )
    mermaid = compile_mermaid(graph, owner="a", repo="b", branch="main")
    assert 'subgraph g_g1["Empty"]' not in mermaid
    assert 'subgraph g_g2["Used"]' in mermaid
