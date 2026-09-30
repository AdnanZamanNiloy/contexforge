from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator, Sequence

import httpx

from core.generation.base_llm import BaseLLM
from core.interfaces.llm import LLM

__all__ = ["FallbackLLM"]

logger = logging.getLogger(__name__)


_RETRYABLE = (
    OSError,  # network-level failures
    TimeoutError,  # request timeouts
    RuntimeError,  # API wrapper errors (httpx, google-generativeai, groq)
    httpx.HTTPStatusError,
    httpx.TransportError,
)

#: How long a rate-limited provider is skipped when it does not say for how long,
#: and the ceiling on any cooldown it does ask for.  A provider told to wait 47s
#: is not a provider worth calling for the next 47s, and one that asks for
#: longer than the ceiling is probed again rather than written off entirely.
_COOLDOWN_DEFAULT_SECONDS = 60.0
_COOLDOWN_MAX_SECONDS = 300.0
#: Google's 429 body carries `{"retryDelay": "47s"}` rather than a header.
_RETRY_DELAY_BODY = re.compile(r'"retryDelay"\s*:\s*"?(\d+(?:\.\d+)?)s"?')


def _cooldown_seconds(exc: Exception) -> float:
    """How long to skip a provider that just rate-limited us."""
    response = getattr(exc, "response", None)
    if response is None:
        return _COOLDOWN_DEFAULT_SECONDS
    # An explicit Retry-After header wins: it is the server's own instruction.
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header), _COOLDOWN_MAX_SECONDS)
        except ValueError:
            pass
    # Otherwise take the hint from the error body, which is where Google puts it.
    try:
        match = _RETRY_DELAY_BODY.search(response.text or "")
    except Exception:  # pragma: no cover - a body that cannot be read
        match = None
    if match:
        return min(float(match.group(1)), _COOLDOWN_MAX_SECONDS)
    return _COOLDOWN_DEFAULT_SECONDS


class FallbackLLM(BaseLLM):
    """Try a chain of LLM providers in order, falling through on failure.

    Accepts either an ordered ``providers`` sequence or the legacy
    ``primary``/``fallback`` keyword arguments (which are normalised into the
    same ordered chain).  Each provider is tried in turn; a provider failure
    that is retryable causes the next provider to be attempted.  For streaming,
    a provider is abandoned for the next one only if it fails *before* the first
    token, since switching mid-stream is unsafe.

    **Rate limiting is remembered.**  A provider that answers 429 is put in a
    cooldown for as long as it asked for, and skipped until then.  Without this
    every single query opened by calling a provider that is known to be
    refusing service: on a free Gemini tier that added a wasted round-trip to
    every request and made a fast answer look like a slow one.  A cooldown is
    used rather than deleting a provider from the chain because the limit is
    transient -- it lifts on its own, and the chain should use the provider
    again without anyone editing configuration.
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
        #: Monotonic deadline per provider index, not wall clock, so a clock
        #: change cannot strand a provider in cooldown forever.
        self._cooldown_until: dict[int, float] = {}
        super().__init__(model="→".join(_model_name(p) for p in self._providers))

    def _available(self) -> list[tuple[int, LLM]]:
        """Providers not in cooldown, always at least one.

        If every provider is cooling down, the one whose cooldown ends soonest is
        offered anyway: waiting indefinitely is worse than trying the least-bad
        option, and a stale deadline is a cheap mistake.
        """
        now = time.monotonic()
        ready = [(i, p) for i, p in enumerate(self._providers) if self._cooldown_until.get(i, 0.0) <= now]
        if ready:
            return ready
        soonest = min(self._providers, key=lambda p: self._cooldown_until.get(self._providers.index(p), 0.0))
        index = self._providers.index(soonest)
        wait = self._cooldown_until.get(index, 0.0) - now
        logger.warning(
            "FallbackLLM: every provider is rate limited; trying %s anyway in %.0fs.",
            _model_name(soonest),
            wait,
        )
        return [(index, soonest)]

    def _note_failure(self, index: int, llm: LLM, exc: Exception) -> None:
        """Remember a rate limit so the next query does not repeat it."""
        status = getattr(exc, "response", None)
        status = getattr(status, "status_code", None)
        if status != 429:
            return
        seconds = _cooldown_seconds(exc)
        self._cooldown_until[index] = time.monotonic() + seconds
        logger.warning(
            "FallbackLLM: %s is rate limited (429); skipping it for %.0fs.",
            _model_name(llm),
            seconds,
        )

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
        failures: list[tuple[str, Exception]] = []
        for idx, llm in self._available():
            try:
                return await llm.generate(prompt, system_prompt=system_prompt)
            except Exception as exc:
                # A non-retryable failure is a request this provider will reject
                # for everyone, so it propagates at once rather than being
                # replayed against every other provider.
                if not isinstance(exc, _RETRYABLE):
                    raise
                self._note_failure(idx, llm, exc)
                logger.warning(
                    "FallbackLLM: provider[%d/%d] (%s) failed for generate (%s: %s) — trying next provider.",
                    idx + 1,
                    len(self._providers),
                    _model_name(llm),
                    type(exc).__name__,
                    exc,
                )
                failures.append((_model_name(llm), exc))
        raise _all_failed("generate", failures) from (failures[-1][1] if failures else None)

    async def _stream_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> AsyncIterator[str]:
        failures: list[tuple[str, Exception]] = []
        for idx, llm in self._available():
            tokens_yielded = 0
            try:
                async for token in llm.stream(prompt, system_prompt=system_prompt):
                    tokens_yielded += 1
                    yield token
                return
            except Exception as exc:
                if not isinstance(exc, _RETRYABLE):
                    raise
                if tokens_yielded > 0:
                    logger.error(
                        "FallbackLLM: provider (%s) failed mid-stream after %d "
                        "token(s) — cannot fall back safely; re-raising.",
                        _model_name(llm),
                        tokens_yielded,
                    )
                    raise
                self._note_failure(idx, llm, exc)
                logger.warning(
                    "FallbackLLM: provider (%s) stream failed before first token (%s: %s) — trying next provider.",
                    _model_name(llm),
                    type(exc).__name__,
                    exc,
                )
                failures.append((_model_name(llm), exc))
        raise _all_failed("stream", failures) from (failures[-1][1] if failures else None)


def _model_name(llm: LLM) -> str:
    return getattr(llm, "_model", type(llm).__name__)


def _all_failed(operation: str, failures: list[tuple[str, Exception]]) -> RuntimeError:
    """The terminal error when every available provider has failed.

    Names each provider that was tried and what it said.  A bare "All providers
    failed" is the least useful message this feature can emit: the whole point of
    a fallback chain is that something specific went wrong with a specific
    provider, and the reader cannot act on either.  Chained from the last
    exception so the original type survives in ``__cause__``.
    """
    if not failures:
        # No provider was available to try — everything is in cooldown.
        return RuntimeError(f"No provider was available to {operation}; all are rate limited.")
    detail = "; ".join(f"{name} ({type(exc).__name__}: {exc})" for name, exc in failures)
    return RuntimeError(f"All {len(failures)} provider(s) failed to {operation}: {detail}")
