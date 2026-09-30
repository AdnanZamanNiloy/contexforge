from pathlib import Path

import pytest

from core.retrieval.rrf_fusion import RRFFusion
from core.storage.bm25_index import BM25Index
from core.storage.faiss_store import FaissStore
from core.types import Chunk, RetrievedChunk


@pytest.mark.asyncio
async def test_bm25_index_round_trip(tmp_path: Path) -> None:
    index = BM25Index(db_path=tmp_path / "bm25.db")
    chunks = [
        Chunk(chunk_id="c1", text="hello world", metadata={}),
        Chunk(chunk_id="c2", text="goodbye world", metadata={}),
    ]
    await index.add(chunks)
    results = await index.search("hello", top_k=5)
    assert results
    assert results[0].chunk.chunk_id == "c1"


@pytest.mark.asyncio
async def test_faiss_store_returns_best_match(tmp_path: Path) -> None:
    store = FaissStore(index_path=tmp_path / "index.faiss")
    chunks = [
        Chunk(chunk_id="c1", text="alpha", metadata={}),
        Chunk(chunk_id="c2", text="beta", metadata={}),
    ]
    vectors = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    await store.add(chunks, vectors)
    results = await store.search([1.0, 0.0, 0.0], top_k=1)
    assert results
    assert results[0].chunk.chunk_id == "c1"


def test_rrf_fusion_merges_scores() -> None:
    fusion = RRFFusion(k=60)
    bm25 = [RetrievedChunk(chunk=Chunk(chunk_id="c1", text="a", metadata={}), score=1.0)]
    dense = [RetrievedChunk(chunk=Chunk(chunk_id="c2", text="b", metadata={}), score=1.0)]
    fused = fusion.fuse(bm25, dense)
    assert {item.chunk.chunk_id for item in fused} == {"c1", "c2"}


# --------------------------------------------------------------------------- #
# Scoped retrieval: exclusion must happen before the result limit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_bm25_scoped_search_is_not_starved_by_other_sources(tmp_path: Path) -> None:
    """A scoped query must find the selected source even when other sources
    dominate the global ranking.

    Regression: the LIMIT used to be applied before the exclusion filter, so
    when unrelated sources filled the top_k the selected source's matching
    chunks were dropped and a scoped query returned nothing.
    """
    index = BM25Index(db_path=tmp_path / "bm25.db")
    other = [
        Chunk(chunk_id=f"other-{i}", text="source source source source", metadata={}, source_id="other")
        for i in range(10)
    ]
    selected = [Chunk(chunk_id="sel-1", text="source material about widgets", metadata={}, source_id="sel")]
    await index.add([*other, *selected])

    # Exclude every source except the selected one.
    results = await index.search("source", top_k=3, exclude_source_ids={"other"})
    assert results, "scoped search returned nothing despite a matching selected chunk"
    assert {r.chunk.source_id for r in results} == {"sel"}
    assert results[0].chunk.chunk_id == "sel-1"


@pytest.mark.asyncio
async def test_faiss_scoped_search_survives_low_global_rank(tmp_path: Path) -> None:
    """The selected source's chunk may rank far outside the global top_k yet
    must still be returned when everything else is excluded."""
    store = FaissStore(index_path=tmp_path / "index.faiss")
    # 20 near-identical "other" vectors all closer to the query than the
    # selected one, plus a distinct selected vector that still points the right
    # way but scores lowest.
    others = [Chunk(chunk_id=f"other-{i}", text="x", metadata={}, source_id="other") for i in range(20)]
    other_vecs = [[1.0, 0.01 * i, 0.0] for i in range(20)]
    selected = Chunk(chunk_id="sel-1", text="y", metadata={}, source_id="sel")
    await store.add([*others, selected], [*other_vecs, [0.6, 0.0, 0.8]])

    results = await store.search([1.0, 0.0, 0.0], top_k=2, exclude_source_ids={"other"})
    assert results, "scoped dense search returned nothing despite a selected chunk"
    assert {r.chunk.source_id for r in results} == {"sel"}
