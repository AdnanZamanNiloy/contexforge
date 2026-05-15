from __future__ import annotations

import logging

from app.config.settings import settings
from core.interfaces.llm import LLM
from observability.tracer import observe

__all__ = ["HydeQueryExpander"]

logger = logging.getLogger(__name__)


class HydeQueryExpander:

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    @observe(name="hyde_generate")
    async def expand(self, question: str) -> str:
        
        if not isinstance(question, str) or not question.strip():
            raise ValueError("HydeQueryExpander.expand received an empty question")

        if not settings.USE_HYDE:
            logger.debug("HyDE disabled via settings — returning original question.")
            return question

        try:
            hypothesis = await self._llm.generate(
                question,
                system_prompt=settings.HYDE_SYSTEM_PROMPT,
            )

            if not hypothesis or not hypothesis.strip():
                logger.warning(
                    "HyDE: LLM returned an empty response for question %r — "
                    "falling back to original question.", question
                )
                return question

            logger.debug(
                "HyDE expanded %d-char question to %d-char hypothesis.",
                len(question), len(hypothesis),
            )
            return hypothesis

        except Exception as exc:
            logger.warning(
                "HyDE generation failed (%s: %s) — falling back to original question.",
                type(exc).__name__, exc,
            )
            return question