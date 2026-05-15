from __future__ import annotations
import logging
from typing import AsyncIterator

from core.generation.base_llm import BaseLLM
from core.interfaces.llm import LLM

__all__ = ["FallbackLLM"]

logger = logging.getLogger(__name__)


_RETRYABLE = (
    OSError,           # network-level failures
    TimeoutError,      # request timeouts
    RuntimeError,      # API wrapper errors (httpx, google-generativeai, groq)
)


class FallbackLLM(BaseLLM):

    def __init__(self, primary: LLM, fallback: LLM) -> None:
        super().__init__(
            model=f"{_model_name(primary)}→{_model_name(fallback)}"
        )
        self._primary = primary
        self._fallback = fallback


    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: str | None,) -> str:
       
        try:
            return await self._primary.generate(prompt, system_prompt=system_prompt)
        except _RETRYABLE as exc:
            logger.warning(
                "Primary LLM (%s) failed for generate (%s: %s) — switching to fallback (%s).",
                _model_name(self._primary),
                type(exc).__name__,
                exc,
                _model_name(self._fallback),
            )
        return await self._fallback.generate(prompt, system_prompt=system_prompt)

    async def _stream_impl(
        self,
        prompt: str,
        system_prompt: str | None,) -> AsyncIterator[str]:
       
        tokens_yielded = 0
        try:
            async for token in self._primary.stream(prompt, system_prompt=system_prompt):
                tokens_yielded += 1
                yield token
            return  

        except _RETRYABLE as exc:
            if tokens_yielded > 0:
               
                logger.error(
                    "Primary LLM (%s) failed mid-stream after %d token(s) — "
                    "cannot fall back safely; re-raising.",
                    _model_name(self._primary),
                    tokens_yielded,
                )
                raise

    
            logger.warning(
                "Primary LLM (%s) stream failed before first token (%s: %s) — "
                "switching to fallback (%s).",
                _model_name(self._primary),
                type(exc).__name__,
                exc,
                _model_name(self._fallback),
            )

        async for token in self._fallback.stream(prompt, system_prompt=system_prompt):
            yield token



def _model_name(llm: LLM) -> str:
    return getattr(llm, "_model", type(llm).__name__)