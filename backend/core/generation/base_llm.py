from __future__ import annotations

import logging
from abc import abstractmethod
from typing import AsyncIterator

from core.interfaces.llm import LLM

__all__ = ["BaseLLM"]

logger = logging.getLogger(__name__)


class BaseLLM(LLM):

    def __init__(self, model: str) -> None:
        if not model or not model.strip():
            raise ValueError(f"{type(self).__name__} received an empty model string")
        self._model = model
        logger.debug("%s initialised with model '%s'.", type(self).__name__, self._model)


    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        self._validate_prompt(prompt)
        logger.debug(
            "%s.generate: model=%s prompt_len=%d",
            type(self).__name__, self._model, len(prompt),
        )
        response = await self._generate_impl(prompt, system_prompt)
        logger.debug(
            "%s.generate: response_len=%d", type(self).__name__, len(response)
        )
        return response

    async def stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        self._validate_prompt(prompt)
        logger.debug(
            "%s.stream: model=%s prompt_len=%d",
            type(self).__name__, self._model, len(prompt),
        )
        async for token in self._stream_impl(prompt, system_prompt):
            yield token

    @abstractmethod
    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def _stream_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError

    @staticmethod
    def _validate_prompt(prompt: str) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("LLM received an empty or non-string prompt")