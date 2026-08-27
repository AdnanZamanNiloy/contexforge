import pytest

from core.retrieval.reranker import Reranker, _MAX_CHUNKS_PER_SOURCE, _diversify
from core.types import Chunk, RetrievedChunk


class FakeModel:
    def predict(self, pairs):
        return [float(len(pair[1])) for pair in pairs]


@pytest.mark.asyncio
async def test_reranker_uses_scores(monkeypatch) -> None:
    reranker = Reranker()

    def fake_load_model():
        reranker._model = FakeModel()

    monkeypatch.setattr(reranker, "_load_model_sync", fake_load_model)

    candidates = [
        RetrievedChunk(chunk=Chunk(chunk_id="c1", text="short", metadata={}), score=0.1),
        RetrievedChunk(chunk=Chunk(chunk_id="c2", text="much longer", metadata={}), score=0.2),
    ]
    results, mean_confidence = await reranker.rerank("query", candidates, top_k=1)
    assert results[0].chunk.chunk_id == "c2"
    assert results[0].rank == 1
    assert mean_confidence > 0


def _chunk(cid: str, sid: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(chunk_id=cid, text=f"{cid} text", source_id=sid),
        score=0.1,
    )


def test_diversify_keeps_every_source_when_one_dominates() -> None:
    """A dominant source cannot crowd a second source out of the top-k."""
    # 6 chunks from "doc-a" score highest, 1 chunk from "doc-b" scores lowest.
    scored = [
        (_chunk(f"a{i}", "doc-a"), 0.9 - 0.1 * i) for i in range(6)
    ] + [(_chunk("b1", "doc-b"), 0.05)]
    top_k = 5

    result = _diversify(scored, top_k)

    assert len(result) == top_k
    # doc-b's single chunk must survive despite the relevance gap.
    assert any(item[0].chunk.source_id == "doc-b" for item in result)


def test_diversify_preserves_relevance_order_for_single_source() -> None:
    """A single-source candidate list is returned in raw relevance order."""
    scored = [
        (_chunk("a1", "doc-a"), 0.9),
        (_chunk("a2", "doc-a"), 0.8),
        (_chunk("a3", "doc-a"), 0.7),
        (_chunk("a4", "doc-a"), 0.6),
    ]
    result = _diversify(scored, top_k=3)
    assert [item[0].chunk.chunk_id for item in result] == ["a1", "a2", "a3"]


def test_diversify_caps_any_one_source() -> None:
    """No single source exceeds the per-source cap in a mixed pool."""
    scored = [
        (_chunk(f"a{i}", "doc-a"), 0.95 - 0.01 * i) for i in range(20)
    ] + [(_chunk(f"b{i}", "doc-b"), 0.4 - 0.01 * i) for i in range(10)]
    result = _diversify(scored, top_k=8)

    src_a = sum(1 for item in result if item[0].chunk.source_id == "doc-a")
    src_b = sum(1 for item in result if item[0].chunk.source_id == "doc-b")
    assert src_a <= _MAX_CHUNKS_PER_SOURCE
    assert src_b >= 1


def test_diversify_keeps_top_k_when_candidates_fit() -> None:
    """When candidates fit in top_k they are all returned."""
    scored = [
        (_chunk("a1", "doc-a"), 0.9),
        (_chunk("b1", "doc-b"), 0.8),
    ]
    assert _diversify(scored, top_k=5) == scored


@pytest.mark.asyncio
async def test_reranker_surfaces_second_source(monkeypatch) -> None:
    """The pipeline reranker surfaces a weaker second source in the top-k."""
    reranker = Reranker()

    def fake_load_model():
        reranker._model = FakeModel()

    monkeypatch.setattr(reranker, "_load_model_sync", fake_load_model)

    # FakeModel scores by text length: longer text → higher score.
    candidates = [
        RetrievedChunk(
            chunk=Chunk(chunk_id=f"a{i}", text="x" * (100 - i), source_id="doc-a"),
            score=0.1,
        )
        for i in range(5)
    ] + [
        RetrievedChunk(
            chunk=Chunk(chunk_id="b1", text="short but distinct source", source_id="doc-b"),
            score=0.1,
        )
    ]
    top_k = 4
    results, _ = await reranker.rerank("query", candidates, top_k=top_k)
    selected_sources = {r.chunk.source_id for r in results}
    assert "doc-b" in selected_sources
