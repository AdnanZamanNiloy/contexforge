from __future__ import annotations

import httpx
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
    chain = FallbackLLM(providers=[_FakeLLM("a", fail=True), _FakeLLM("b"), _FakeLLM("c")])
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


# --------------------------------------------------------------------------- #
# Rate-limit cooldown
#
# A provider told to refuse service for 47 seconds was being called at the head
# of every single query, so every query began with a doomed round-trip. The
# chain now remembers, which is what makes the answer feel fast rather than
# merely correct.
# --------------------------------------------------------------------------- #


def _rate_limited(status: int = 429, headers: dict | None = None, body: str = "") -> Exception:
    request = httpx.Request("POST", "https://example.invalid/generate")
    response = httpx.Response(status, headers=headers or {}, content=body, request=request)
    return httpx.HTTPStatusError("rate limited", request=request, response=response)


class _CountingLLM(_FakeLLM):
    """Records how many times it was actually called."""

    def __init__(self, name: str, *, error: Exception | None = None) -> None:
        super().__init__(name)
        self.calls = 0
        self._error = error

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return f"answer-from-{self._model}"

    async def stream(self, prompt: str, system_prompt: str | None = None):
        self.calls += 1
        if self._error is not None:
            raise self._error
        yield f"token-from-{self._model}"


@pytest.mark.asyncio
async def test_a_rate_limited_provider_is_not_called_again() -> None:
    limited = _CountingLLM("gemini", error=_rate_limited(headers={"retry-after": "47"}))
    healthy = _CountingLLM("groq")
    chain = FallbackLLM(providers=[limited, healthy])

    assert await chain.generate("q1") == "answer-from-groq"
    assert limited.calls == 1  # tried once, found rate limited

    # Every later query goes straight to the provider that can answer.
    for _ in range(4):
        assert await chain.generate("q") == "answer-from-groq"
    assert limited.calls == 1, "a provider in cooldown must not be re-tried"
    assert healthy.calls == 5


@pytest.mark.asyncio
async def test_cooldown_reads_the_delay_google_puts_in_the_body() -> None:
    # Google answers 429 with `{"retryDelay": "47s"}` and no Retry-After header.
    body = '{"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "47s"}]}}'
    limited = _CountingLLM("gemini", error=_rate_limited(body=body))
    chain = FallbackLLM(providers=[limited, _CountingLLM("groq")])

    await chain.generate("q")
    remaining = chain._cooldown_until[0] - _monotonic_ish()
    assert 40 < remaining <= 47, f"expected the body's own 47s window, got {remaining:.1f}"


def _monotonic_ish() -> float:
    import time

    return time.monotonic()


@pytest.mark.asyncio
async def test_cooldown_expires_and_the_provider_is_tried_again() -> None:
    import time

    limited = _CountingLLM("gemini", error=_rate_limited(headers={"retry-after": "0"}))
    healthy = _CountingLLM("groq")
    chain = FallbackLLM(providers=[limited, healthy])

    await chain.generate("q")
    assert limited.calls == 1
    time.sleep(0.01)  # a zero-second window has elapsed
    await chain.generate("q")
    assert limited.calls == 2, "a limit that has lifted should not keep the provider out"


@pytest.mark.asyncio
async def test_a_non_429_failure_does_not_trigger_a_cooldown() -> None:
    # Only rate limiting is remembered. A transient network blip should not
    # take a working provider out of rotation for a minute.
    flaky = _CountingLLM("a", error=OSError("connection reset"))
    healthy = _CountingLLM("b")
    chain = FallbackLLM(providers=[flaky, healthy])

    await chain.generate("q1")
    await chain.generate("q2")
    assert flaky.calls == 2
    assert not chain._cooldown_until


@pytest.mark.asyncio
async def test_all_providers_cooling_down_still_tries_the_soonest() -> None:
    a = _CountingLLM("a", error=_rate_limited(headers={"retry-after": "300"}))
    b = _CountingLLM("b", error=_rate_limited(headers={"retry-after": "300"}))
    chain = FallbackLLM(providers=[a, b])

    with pytest.raises(httpx.HTTPStatusError):
        await chain.generate("q")  # both refuse

    calls_before = a.calls + b.calls
    with pytest.raises(httpx.HTTPStatusError):
        await chain.generate("q")  # still tried, rather than failing outright
    assert a.calls + b.calls > calls_before, "waiting indefinitely is worse than trying"


@pytest.mark.asyncio
async def test_streaming_also_honours_the_cooldown() -> None:
    limited = _CountingLLM("gemini", error=_rate_limited(headers={"retry-after": "30"}))
    healthy = _CountingLLM("groq")
    chain = FallbackLLM(providers=[limited, healthy])

    assert [t async for t in chain.stream("q1")] == ["token-from-groq"]
    assert [t async for t in chain.stream("q2")] == ["token-from-groq"]
    assert limited.calls == 1
