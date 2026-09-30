"""End-to-end checks that the grounding penalty is wired into ``answer()``.

The unit tests for ``_grounded_confidence`` cover the arithmetic; these cover
the integration. A penalty that is computed correctly but never called is
still a bug, and the only way to know it is called is to drive the real
pipeline entry point.
"""

from __future__ import annotations

import pytest

import core.orchestrator as orchestrator_module
from core.generation.prompt_builder import PromptBuilder
from core.orchestrator import Orchestrator
from core.types import Chunk, RerankedChunk


class _StubLLM:
    """LLM stub whose answer is supplied by the test."""

    text = ""

    async def generate(self, prompt, system_prompt=None):
        return self.text

    async def stream(self, prompt, system_prompt=None):
        yield self.text

    @property
    def model(self):
        return "stub"


def _orchestrator_returning(llm_text: str, context: str) -> Orchestrator:
    orch = Orchestrator.__new__(Orchestrator)
    llm = _StubLLM()
    llm.text = llm_text
    orch._llm = llm
    orch._prompt_builder = PromptBuilder()

    async def fake_retrieve(*args, **kwargs):
        reranked = [
            RerankedChunk(
                chunk=Chunk(chunk_id=f"c{i}", text=context, source_id="s"),
                score=0.95,
                rank=i,
            )
            for i in range(1, 4)
        ]
        return reranked, {"total_ms": 1.0}, 0.95

    orch.retrieve_context = fake_retrieve
    return orch


@pytest.mark.asyncio
async def test_answer_path_applies_grounding_penalty() -> None:
    """An answer inventing figures must not keep a 0.95 retrieval score."""
    orch = _orchestrator_returning(
        "The service handled 99.99% of requests at 12.5 ms in 2024-06-01.",
        "The backend exposes POST /predict.",
    )

    result = await orch.answer("How fast is the service?")

    assert result.confidence.answer_confidence < 0.95, "invented figures must reduce confidence"
    assert result.confidence.source_coverage != "Excellent", "the coverage label must track the adjusted number"


@pytest.mark.asyncio
async def test_answer_path_leaves_a_faithful_answer_alone() -> None:
    """The penalty must not touch an answer the corpus supports."""
    orch = _orchestrator_returning(
        "The backend exposes POST /predict.",
        "The backend exposes POST /predict.",
    )

    result = await orch.answer("How does the backend serve predictions?")

    assert result.confidence.answer_confidence == 0.95
    assert result.confidence.source_coverage == "Excellent"


@pytest.mark.asyncio
async def test_answer_path_explains_a_penalised_score() -> None:
    """A penalised answer must say so, otherwise the drop looks arbitrary."""
    orch = _orchestrator_returning(
        "The service handled 99.99% of requests at 12.5 ms in 2024-06-01.",
        "The backend exposes POST /predict.",
    )

    result = await orch.answer("How fast is the service?")

    assert result.confidence.low_confidence_reason is not None
    assert "could not be found in your sources" in result.confidence.low_confidence_reason


@pytest.mark.asyncio
async def test_answer_path_does_not_explain_a_healthy_score() -> None:
    """No explanation is attached when nothing went wrong."""
    orch = _orchestrator_returning(
        "The backend exposes POST /predict.",
        "The backend exposes POST /predict.",
    )

    result = await orch.answer("How does the backend serve predictions?")

    assert result.confidence.low_confidence_reason is None


@pytest.mark.asyncio
async def test_grounding_report_is_computed_once() -> None:
    """The penalty and the explanation must not disagree.

    They share one report, so a claim can never be penalised in the number and
    absent from the message. Counting the calls pins that down.
    """
    orch = _orchestrator_returning(
        "The service handled 99.99% of requests at 12.5 ms in 2024-06-01.",
        "The backend exposes POST /predict.",
    )
    calls = 0
    real = orchestrator_module.check_grounding

    def counting(answer: str, chunks: list[str]):
        nonlocal calls
        calls += 1
        return real(answer, chunks)

    orchestrator_module.check_grounding = counting
    try:
        await orch.answer("How fast is the service?")
    finally:
        orchestrator_module.check_grounding = real

    assert calls == 1, "the answer should be scanned for unsupported claims exactly once"
