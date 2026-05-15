import pytest

from core.retrieval.reranker import Reranker
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
    results = await reranker.rerank("query", candidates, top_k=1)
    assert results[0].chunk.chunk_id == "c2"
    assert results[0].rank == 1
