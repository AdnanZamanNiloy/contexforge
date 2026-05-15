from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from app.config.settings import settings
from core.generation.base_llm import BaseLLM
from observability.tracer import observe

__all__ = ["GroqLLM"]

logger = logging.getLogger(__name__)


_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES      = 3
_RETRY_BASE_DELAY = 1.0   # seconds (doubles each attempt)
_RETRY_MAX_DELAY  = 16.0  # seconds

_GENERATE_TIMEOUT = httpx.Timeout(timeout=60.0)
_STREAM_TIMEOUT   = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)

_CLEAN_FINISH_REASONS = {"stop", ""}




class GroqLLM(BaseLLM):
   

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model or settings.GROQ_MODEL)
        self._temperature = temperature
        self._max_tokens  = max_tokens
        # Auth header lives on the client — built once, never leaked into URLs.
        self._client = http_client or httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            timeout=_GENERATE_TIMEOUT,
        )


    async def __aenter__(self) -> "GroqLLM":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

   

    @observe(name="groq_generate")
    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> str:
        payload = self._build_payload(prompt, system_prompt, stream=False)
        data    = await self._post_with_retry(_GROQ_URL, payload)
        return self._extract_text(data, context="generate")

    @observe(name="groq_stream")
    async def _stream_impl(
        self,
        prompt: str,
        system_prompt: str | None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(prompt, system_prompt, stream=True)

        async with self._client.stream(
            "POST",
            _GROQ_URL,
            json=payload,
            timeout=_STREAM_TIMEOUT,
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "groq_stream: HTTP %d — %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                raise

            async for line in response.aiter_lines():
                if not line:
                    continue

               
                raw = line.removeprefix("data: ").strip()
                if not raw or raw == "[DONE]":
                    break

                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "groq_stream: skipped non-JSON SSE line: %.120s", raw
                    )
                    continue

            
                choice = chunk.get("choices", [{}])[0]
                finish = choice.get("finish_reason") or ""
                if finish and finish not in _CLEAN_FINISH_REASONS:
                    logger.warning(
                        "groq_stream: non-clean finish_reason=%s", finish
                    )

                delta = choice.get("delta", {}).get("content")
                if delta:
                    yield delta

 
    async def _post_with_retry(self, url: str, payload: dict) -> dict:
    
        delay     = _RETRY_BASE_DELAY
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.post(
                    url, json=payload, timeout=_GENERATE_TIMEOUT
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                    logger.error(
                        "groq_generate: HTTP %d on attempt %d/%d — %s",
                        status, attempt, _MAX_RETRIES, exc.response.text,
                    )
                    raise
                wait = min(delay, _RETRY_MAX_DELAY)
                logger.warning(
                    "groq_generate: HTTP %d — retrying in %.1fs (attempt %d/%d)",
                    status, wait, attempt, _MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                delay   *= 2
                last_exc = exc

            except httpx.TransportError as exc:
                if attempt == _MAX_RETRIES:
                    logger.error(
                        "groq_generate: transport error on attempt %d/%d: %s",
                        attempt, _MAX_RETRIES, exc,
                    )
                    raise
                wait = min(delay, _RETRY_MAX_DELAY)
                logger.warning(
                    "groq_generate: transport error — retrying in %.1fs (%s)",
                    wait, exc,
                )
                await asyncio.sleep(wait)
                delay   *= 2
                last_exc = exc

        raise RuntimeError("Retry loop exited without returning") from last_exc

   
    def _build_payload(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        stream: bool,
    ) -> dict:
        
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model":       self._model,
            "messages":    messages,
            "stream":      stream,
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens

        return payload

    @staticmethod
    def _extract_text(data: dict, *, context: str = "") -> str:
      
        choices = data.get("choices")
        if not choices:
            logger.warning("groq[%s]: response contained no choices", context)
            return ""

        choice = choices[0]
        finish = choice.get("finish_reason", "")

        if finish and finish not in _CLEAN_FINISH_REASONS:
            logger.warning(
                "groq[%s]: non-clean finish_reason=%s — content may be "
                "truncated or filtered",
                context, finish,
            )

        content = choice.get("message", {}).get("content")
        if content is None:
            logger.warning("groq[%s]: choice had no message content", context)
            return ""

        return content