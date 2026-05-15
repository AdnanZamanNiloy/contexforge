from pathlib import Path

import numpy as np
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
