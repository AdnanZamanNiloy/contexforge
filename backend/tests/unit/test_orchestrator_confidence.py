from __future__ import annotations

import pytest

from core.orchestrator import Orchestrator, _is_chitchat, _is_vague_query
from core.types import Chunk, RerankedChunk


@pytest.mark.parametrize(
    "question, expected",
    [
        ("hello", True),
        ("hi there", True),
        ("thanks!", True),
        ("good morning", True),
        ("summarize this", False),  # carries an information request
        ("give me details about it", False),
        ("What projects does Adnan have?", False),
        ("hello, summarize the projects", False),  # content word present
    ],
)
def test_is_chitchat(question: str, expected: bool) -> None:
    assert _is_chitchat(question) is expected


@pytest.mark.parametrize(
    "question, expected",
    [
        ("summarize this resume", True),
        ("tell me about source", True),
        ("overview", True),
        ("What date was MBSTU established?", False),
        ("Where did Adnan study?", False),
    ],
)
def test_is_vague_query(question: str, expected: bool) -> None:
    assert _is_vague_query(question) is expected


def _reranked(source_id: str, rank: int) -> RerankedChunk:
    return RerankedChunk(
        chunk=Chunk(chunk_id=f"{source_id}:{rank}", text=f"chunk {source_id}:{rank}", source_id=source_id),
        score=0.1,
        rank=rank,
    )


@pytest.mark.asyncio
async def test_focus_boost_single_source() -> None:
    """A query answered from one dominant source is boosted to Excellent."""
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [_reranked("src", i) for i in range(1, 6)]  # focus = 1.0
    confidence = await orch._apply_confidence("tell me about source", reranked, base=0.20)
    assert confidence == 0.85


@pytest.mark.asyncio
async def test_focus_boost_moderate() -> None:
    """A clearly-dominant source (75% focus) maps to the Strong tier."""
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [
        _reranked("src", i) for i in range(1, 4)  # 3 chunks
    ] + [_reranked("other", i) for i in range(1, 2)]  # 1 chunk → 0.75 focus
    confidence = await orch._apply_confidence("tell me about source", reranked, base=0.20)
    assert confidence == 0.65


@pytest.mark.asyncio
async def test_no_boost_when_off_topic() -> None:
    """Low per-chunk relevance (below the gate) means off-topic — no boost."""
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [_reranked("src", i) for i in range(1, 6)]  # focus = 1.0
    confidence = await orch._apply_confidence("meaning of life", reranked, base=0.10)
    assert confidence == 0.10


@pytest.mark.asyncio
async def test_no_boost_when_low_focus() -> None:
    """Chunks spread across sources (low focus) are not boosted."""
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [_reranked("src", i) for i in range(1, 3)] + [_reranked("other", i) for i in range(1, 3)]  # 0.5 focus
    confidence = await orch._apply_confidence("compare the two", reranked, base=0.30)
    assert confidence == 0.30


@pytest.mark.asyncio
async def test_no_boost_when_relevance_already_high() -> None:
    """Strong relevance is never lowered by the focus logic."""
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [_reranked("src", i) for i in range(1, 4)]  # focus = 1.0
    confidence = await orch._apply_confidence("a specific question", reranked, base=0.9453)
    assert confidence == 0.9453


@pytest.mark.asyncio
async def test_no_boost_for_chitchat() -> None:
    """Chitchat never benefits from the focus boost."""
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [_reranked("src", 1)]
    confidence = await orch._apply_confidence("hello", reranked, base=0.20)
    assert confidence == 0.20
