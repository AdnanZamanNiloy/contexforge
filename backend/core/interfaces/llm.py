from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLM(ABC):
    """LLM interface."""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, prompt: str, system_prompt: str | None = None) -> AsyncIterator[str]:
        raise NotImplementedError
