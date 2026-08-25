from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import AsyncIterator

import httpx

from core.generation.base_llm import BaseLLM
from core.interfaces.llm import LLM

__all__ = ["FallbackLLM"]

logger = logging.getLogger(__name__)


_RETRYABLE = (
    OSError,            # network-level failures
    TimeoutError,       # request timeouts
    RuntimeError,       # API wrapper errors (httpx, google-generativeai, groq)
    httpx.HTTPStatusError,
    httpx.TransportError,
)


class FallbackLLM(BaseLLM):
    """Try a chain of LLM providers in order, falling through on failure.

    Accepts either an ordered ``providers`` sequence or the legacy
    ``primary``/``fallback`` keyword arguments (which are normalised into the
    same ordered chain).  Each provider is tried in turn; a provider failure
    that is retryable causes the next provider to be attempted.  For streaming,
    a provider is abandoned for the next one only if it fails *before* the first
    token, since switching mid-stream is unsafe.
    """

    def __init__(
        self,
        primary: LLM | None = None,
        fallback: LLM | None = None,
        *,
        providers: Sequence[LLM] | None = None,
    ) -> None:
        if providers is not None:
            chain: list[LLM] = list(providers)
        else:
            chain = [p for p in (primary, fallback) if p is not None]
        if not chain:
            raise ValueError("FallbackLLM requires at least one provider")
        self._providers = tuple(chain)
        super().__init__(model="→".join(_model_name(p) for p in self._providers))

    async def aclose(self) -> None:
        """Close the underlying HTTP clients of every provider."""
        for llm in self._providers:
            close = getattr(llm, "aclose", None)
            if close is not None:
                await close()

    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> str:
        last_exc: Exception | None = None
        for idx, llm in enumerate(self._providers):
            try:
                return await llm.generate(prompt, system_prompt=system_prompt)
            except Exception as exc:  # noqa: BLE001 - fall through to next provider
                if not isinstance(exc, _RETRYABLE) or idx == len(self._providers) - 1:
                    raise
                logger.warning(
                    "FallbackLLM: provider[%d/%d] (%s) failed for generate "
                    "(%s: %s) — trying next provider.",
                    idx + 1, len(self._providers),
                    _model_name(llm), type(exc).__name__, exc,
                )
                last_exc = exc
        raise RuntimeError("All providers failed") from last_exc

    async def _stream_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> AsyncIterator[str]:
        last_exc: Exception | None = None
        for idx, llm in enumerate(self._providers):
            tokens_yielded = 0
            try:
                async for token in llm.stream(prompt, system_prompt=system_prompt):
                    tokens_yielded += 1
                    yield token
                return
            except Exception as exc:  # noqa: BLE001
                if not isinstance(exc, _RETRYABLE) or idx == len(self._providers) - 1:
                    raise
                if tokens_yielded > 0:
                    logger.error(
                        "FallbackLLM: provider (%s) failed mid-stream after %d "
                        "token(s) — cannot fall back safely; re-raising.",
                        _model_name(llm), tokens_yielded,
                    )
                    raise
                logger.warning(
                    "FallbackLLM: provider (%s) stream failed before first token "
                    "(%s: %s) — trying next provider.",
                    _model_name(llm), type(exc).__name__, exc,
                )
                last_exc = exc
        raise RuntimeError("All providers failed to stream") from last_exc


def _model_name(llm: LLM) -> str:
    return getattr(llm, "_model", type(llm).__name__)
