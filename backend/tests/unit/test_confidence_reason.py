"""Tests for the low-confidence explanation sent to the UI.

A confidence score on its own is not actionable: "15%" gives a user no way to
tell whether their question, their source selection or the pipeline is
responsible, so they tend to conclude the tool is broken. ``_low_confidence_reason``
names the cause and the next step.

The cases below are the three that were actually observed in the app, each
reproduced from a real question against a real index:

* ``give me details about it`` over the JUST article scored 0.15 with a top chunk
  relevance of 0.03 - a question that names no subject at all.
* The same source asked about by name scored 0.97, so the score is not a
  property of the source.
* A Bengali question over Bengali passages scores 0.98 while its English
  translation scores 0.16, because the cross-encoder is English-only.
"""

from __future__ import annotations

import pytest

from core.orchestrator import Orchestrator
from core.types import Chunk, RerankedChunk


def _orchestrator() -> Orchestrator:
    """A confidence-only orchestrator; the explanation reads no collaborators."""
    return Orchestrator.__new__(Orchestrator)


def _reranked(source_id: str, rank: int, *, score: float = 0.5) -> RerankedChunk:
    return RerankedChunk(
        chunk=Chunk(chunk_id=f"{source_id}:{rank}", text=f"chunk {source_id}:{rank}", source_id=source_id),
        score=score,
        rank=rank,
    )


def test_underspecified_question_explains_the_missing_topic() -> None:
    """The real failing case: a pronoun-only follow-up gets the topic hint."""
    reason = _orchestrator()._low_confidence_reason(
        "give me details about it",
        [_reranked("src", i) for i in range(1, 6)],
        0.15,
    )
    assert reason is not None
    # It must point at the query, not at the sources the user carefully selected.
    assert "no topic words" in reason
    assert "Name the subject" in reason


def test_ungrounded_claims_take_priority() -> None:
    """An invented figure is the more useful thing to report, even on a vague question."""
    reason = _orchestrator()._low_confidence_reason(
        "give me details about it",
        [_reranked("src", i) for i in range(1, 6)],
        0.15,
        ungrounded_claims=2,
    )
    assert reason is not None
    assert "could not be found in your sources" in reason
    # Singular/plural agreement: 1 claim must not read as "1 specific details".
    assert "2 specific details" in reason


@pytest.mark.parametrize("claims, expected_fragment", [(1, "1 specific detail"), (3, "3 specific details")])
def test_ungrounded_claim_count_is_pluralised(claims: int, expected_fragment: str) -> None:
    reason = _orchestrator()._low_confidence_reason(
        "what was the budget",
        [_reranked("src", 1)],
        0.20,
        ungrounded_claims=claims,
    )
    assert reason is not None
    assert expected_fragment in reason


def test_no_chunks_is_reported_distinctly() -> None:
    """Nothing retrieved is a different problem from a poor match."""
    reason = _orchestrator()._low_confidence_reason("what is the retention policy", [], 0.0)
    assert reason is not None
    assert "No passages matched" in reason


def test_poor_match_falls_back_to_generic_guidance() -> None:
    """A named but unmatched question gets match advice, not pronoun advice."""
    reason = _orchestrator()._low_confidence_reason(
        "When did JUST open and who was its first vice chancellor?",
        [_reranked("src", i) for i in range(1, 6)],
        0.16,
    )
    assert reason is not None
    assert "did not closely match" in reason


def test_healthy_confidence_gets_no_explanation() -> None:
    """A good score speaks for itself; a caption would only be noise."""
    assert _orchestrator()._low_confidence_reason("tell me about JUST", [_reranked("src", 1)], 0.97) is None


def test_explanation_ceiling_is_inclusive() -> None:
    """0.40 sits exactly on the lowest coverage label, so it still explains."""
    orch = _orchestrator()
    assert orch._low_confidence_reason("tell me about JUST", [_reranked("src", 1)], 0.40) is not None
    assert orch._low_confidence_reason("tell me about JUST", [_reranked("src", 1)], 0.401) is None


@pytest.mark.parametrize(
    "question, expected",
    [
        # The real questions, all of which name no subject of their own.
        ("give me details about it", True),
        ("tell me about it", True),
        ("what is this", True),
        ("more about that", True),
        ("summarize them", True),
        # A subject is present, so these are already answerable and must be
        # left alone. Rewriting these would corrupt a working query.
        ("what did JUST do in 2008", False),
        ("who is the vice chancellor", False),
        # Long enough to carry its own subject even with a pronoun in it.
        ("what are the admission requirements for the engineering programme", False),
        # No pronoun at all.
        ("tell me about the university", False),
    ],
)
def test_is_underspecified_question(question: str, expected: bool) -> None:
    assert _orchestrator()._is_underspecified_question(question) is expected


@pytest.mark.parametrize("question", ["", "   ", "!!?"])
def test_blank_questions_are_not_underspecified(question: str) -> None:
    """A blank question has no pronoun, so it must not be labelled as needing one."""
    assert _orchestrator()._is_underspecified_question(question) is False


def test_bengali_question_is_not_flagged_underspecified() -> None:
    """Bengali tokens must survive tokenization, or every Bengali question reads as vague."""
    assert _orchestrator()._is_underspecified_question("এটা সম্পর্কে আরও বিস্তারিত বলুন") is False


def test_reason_is_carried_on_the_metrics_object() -> None:
    """The field has to reach the response, not just exist on the orchestrator."""
    metrics = _orchestrator()._build_confidence([_reranked("src", 1)], 0.15)
    assert metrics.low_confidence_reason is None
