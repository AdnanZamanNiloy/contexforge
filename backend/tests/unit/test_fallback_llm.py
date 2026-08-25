from __future__ import annotations

import pytest

from core.generation.fallback_llm import FallbackLLM
from core.generation.openai_compat_llm import OpenAICompatLLM
from core.interfaces.llm import LLM


class _FakeLLM(LLM):
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self._model = name
        self._fail = fail

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        if self._fail:
            raise OSError("simulated provider failure")
        return f"answer-from-{self._model}"

    async def stream(self, prompt: str, system_prompt: str | None = None):
        if self._fail:
            raise OSError("simulated provider failure")
        yield f"token-from-{self._model}"


@pytest.mark.asyncio
async def test_fallback_falls_through_to_next_provider() -> None:
    chain = FallbackLLM(
        providers=[_FakeLLM("a", fail=True), _FakeLLM("b"), _FakeLLM("c")]
    )
    assert await chain.generate("hi") == "answer-from-b"


@pytest.mark.asyncio
async def test_fallback_returns_first_success() -> None:
    chain = FallbackLLM(providers=[_FakeLLM("a"), _FakeLLM("b")])
    assert await chain.generate("hi") == "answer-from-a"


@pytest.mark.asyncio
async def test_fallback_reraises_when_all_providers_fail() -> None:
    chain = FallbackLLM(providers=[_FakeLLM("a", fail=True), _FakeLLM("b", fail=True)])
    with pytest.raises(OSError):
        await chain.generate("hi")


@pytest.mark.asyncio
async def test_fallback_stream_uses_first_provider() -> None:
    chain = FallbackLLM(providers=[_FakeLLM("a"), _FakeLLM("b")])
    tokens = [t async for t in chain.stream("hi")]
    assert tokens == ["token-from-a"]


def test_openai_compat_requires_a_key() -> None:
    with pytest.raises(ValueError):
        OpenAICompatLLM(
            model="m",
            api_url="https://example.com/chat/completions",
            api_key="",
        )


def test_openai_compat_accepts_a_key() -> None:
    llm = OpenAICompatLLM(
        model="m",
        api_url="https://example.com/chat/completions",
        api_key="sk-abc123",
    )
    assert llm._api_url.endswith("/chat/completions")
