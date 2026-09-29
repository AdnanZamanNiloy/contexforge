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


def _reranked(source_id: str, rank: int, *, score: float = 0.5) -> RerankedChunk:
    """Build one retrieved chunk.

    The default score is 0.5 - a genuine match - because the focus gate reads
    the top chunk score rather than the reranker's floored display value. A stub
    claiming ``base=0.20`` while scoring every chunk ``0.1`` would describe a
    non-match and then ask for a boost.
    """
    return RerankedChunk(
        chunk=Chunk(chunk_id=f"{source_id}:{rank}", text=f"chunk {source_id}:{rank}", source_id=source_id),
        score=score,
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
        _reranked("src", i)
        for i in range(1, 4)  # 3 chunks
    ] + [_reranked("other", i) for i in range(1, 2)]  # 1 chunk → 0.75 focus
    confidence = await orch._apply_confidence("tell me about source", reranked, base=0.20)
    assert confidence == 0.65


@pytest.mark.asyncio
async def test_no_boost_when_off_topic() -> None:
    """Low per-chunk relevance (below the gate) means off-topic — no boost."""
    orch = Orchestrator.__new__(Orchestrator)
    # Chunks that genuinely did not match, matching the low reported base.
    reranked = [_reranked("src", i, score=0.05) for i in range(1, 6)]  # focus = 1.0
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


@pytest.mark.asyncio
async def test_overview_boost_still_requires_some_relevance() -> None:
    """Source dominance must not manufacture confidence on a non-match.

    "What does this repository do?" is classified as a corpus overview (it is
    short and contains a corpus-reference marker), and all five retrieved chunks
    came from one repo, so focus was 1.0. The cross-encoder still scored the
    best chunk 0.0696 — effectively no match. The overview branch used to
    bypass the relevance gate entirely, so this reported 0.85 "Excellent" while
    retrieval had found nothing relevant. Concentration indicates *which*
    source was read; it is not evidence that the question was answered.
    """
    orch = Orchestrator.__new__(Orchestrator)
    # Real chunks from the reproduced run: the best scored 0.0153, and the
    # reranker had already lifted its reported confidence to the 0.15 display
    # floor. That floored value is what made the old gate unreachable, so the
    # test reproduces it exactly rather than passing a convenient number.
    reranked = [
        RerankedChunk(
            chunk=Chunk(
                chunk_id=f"repo:diabetescare-ai:{i}",
                text=f"chunk {i}",
                source_id="repo:diabetescare-ai",
            ),
            score=score,
            rank=i,
        )
        for i, score in enumerate((0.0153, 0.0121, 0.0094, 0.0088, 0.0071), start=1)
    ]

    confidence = await orch._apply_confidence(
        "What does this repository do?",
        reranked,
        base=0.15,
    )

    assert confidence == 0.15, (
        "a 0.0153 top score must not be reported as a boosted high-confidence "
        "answer just because every chunk came from the same repository"
    )


@pytest.mark.asyncio
async def test_overview_boost_still_applies_above_the_overview_gate() -> None:
    """The reduced gate must not disable the boost it exists to permit.

    A genuine "summarize this" over a small, fully-retrieved source scores low
    on the cross-encoder but really is well grounded. That case must keep its
    boost, otherwise fixing the defect above would just remove the feature.
    """
    orch = Orchestrator.__new__(Orchestrator)
    reranked = [_reranked("src", i) for i in range(1, 6)]  # focus = 1.0

    confidence = await orch._apply_confidence("summarize this", reranked, base=0.20)

    assert confidence == 0.85, "the corpus-overview boost must still work when relevance is real"


@pytest.mark.asyncio
async def test_overview_gate_sits_below_the_ordinary_gate() -> None:
    """The overview floor is a relaxation, not a hole.

    If the two gates ever equalise, the distinct constant stops earning its
    keep and the special case is just dead configuration.
    """
    assert Orchestrator._OVERVIEW_RELEVANCE_GATE < Orchestrator._FOCUS_RELEVANCE_GATE


def test_unsupported_claims_reduce_confidence() -> None:
    """A high retrieval score must not certify an answer that invents figures.

    Retrieval confidence answers "how well did the chunks match the question".
    It cannot answer "is the answer supported by them", so an answer asserting
    numbers found nowhere in the corpus has to be penalised here. Without this,
    a fluent answer full of invented specifics reports exactly as confidently as
    a faithful one.
    """
    orch = Orchestrator.__new__(Orchestrator)
    # High retrieval confidence, but the retrieved text supports nothing the
    # invented answer claims.
    reranked = [
        RerankedChunk(
            chunk=Chunk(
                chunk_id=f"c{i}",
                text="The backend exposes a single prediction endpoint.",
                source_id="src",
            ),
            score=0.95,
            rank=i,
        )
        for i in range(1, 6)
    ]

    honest = orch._grounded_confidence(
        0.95,
        "The backend exposes a single prediction endpoint.",
        reranked,
    )
    invented = orch._grounded_confidence(
        0.95,
        "Accuracy reached 97.06% on 2024-03-15 after tuning.",
        reranked,
    )

    assert honest == 0.95, "a faithful answer must keep its confidence"
    assert invented < 0.95, "invented specifics must reduce confidence"
    assert invented >= orch._MIN_CONFIDENCE_AFTER_UNGROUNDED


def test_grounding_penalty_reads_full_chunk_text() -> None:
    """A figure past the 200-char preview must still be found.

    The source payload only carries ``text_preview``; checking that instead of
    the full chunk would mark a correctly-sourced number as invented purely
    because of where it landed in the text.
    """
    from core.types import Chunk, RerankedChunk

    orch = Orchestrator.__new__(Orchestrator)
    padding = "Lorem ipsum dolor sit amet. " * 20
    text = f"{padding}The model reports 97.06% accuracy."
    assert text[:200].find("97.06") == -1, "fixture must place the figure past the preview"

    reranked = [
        RerankedChunk(
            chunk=Chunk(chunk_id=f"c{i}", text=text, source_id="src"),
            score=0.95,
            rank=i,
        )
        for i in range(1, 4)
    ]

    assert orch._grounded_confidence(0.95, "It reports 97.06% accuracy.", reranked) == 0.95


def test_penalty_scales_with_how_much_is_unsupported() -> None:
    """One stray number should not erase an otherwise well-grounded answer."""
    orch = Orchestrator.__new__(Orchestrator)
    # Chunk is a frozen dataclass, so the fixture is built with the text it
    # needs rather than mutated after construction.
    reranked = [
        RerankedChunk(
            chunk=Chunk(
                chunk_id=f"c{i}",
                text="Accuracy was 97.06% overall.",
                source_id="src",
            ),
            score=0.95,
            rank=i,
        )
        for i in range(1, 4)
    ]

    one_bad = orch._grounded_confidence(0.95, "It is 97.06% accurate, released 2024-03-15.", reranked)
    all_bad = orch._grounded_confidence(0.95, "It is 12.5% accurate, released 2024-03-15.", reranked)

    assert one_bad < 0.95
    assert all_bad < one_bad, "more unsupported claims must cost more confidence"


@pytest.mark.asyncio
async def test_retrieve_context_skips_the_knowledge_base_when_disabled() -> None:
    """With ``use_knowledge_base=False`` no retrieval happens at all.

    Regression guard for unscoped chat: with no source selected the answer must
    come from general knowledge, never from chunks the user did not choose.
    """
    orch = Orchestrator.__new__(Orchestrator)

    reranked, timings, mean_confidence = await orch.retrieve_context(
        "tell me about source",
        use_knowledge_base=False,
    )

    assert reranked == []
    assert timings == {}
    assert mean_confidence == 0.0
