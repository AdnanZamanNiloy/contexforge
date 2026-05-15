from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from app.config.settings import settings
from core.generation.base_llm import BaseLLM
from observability.tracer import observe

logger = logging.getLogger(__name__)


_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0   
_RETRY_MAX_DELAY  = 16.0 

_GENERATE_TIMEOUT = httpx.Timeout(timeout=60.0)
_STREAM_TIMEOUT   = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)


class GeminiLLM(BaseLLM):

    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        http_client: httpx.AsyncClient | None = None,) -> None:
        super().__init__(model or settings.GEMINI_MODEL)
        self._temperature = temperature
        self._max_tokens  = max_tokens
        
        self._client = http_client or httpx.AsyncClient(
            headers={"x-goog-api-key": settings.GOOGLE_API_KEY},
            timeout=_GENERATE_TIMEOUT,
        )

    
    async def __aenter__(self) -> "GeminiLLM":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()


    @observe(name="gemini_generate")
    async def _generate_impl(
        self,
        prompt: str,
        system_prompt: str | None,) -> str:

        payload = self._build_payload(prompt, system_prompt)
        data = await self._post_with_retry(
            self._endpoint("generateContent"),
            payload,
            timeout=_GENERATE_TIMEOUT,
        )
        return self._extract_text(data, context="generate")

    @observe(name="gemini_stream")
    async def _stream_impl(
        self,
        prompt: str,
        system_prompt: str | None,) -> AsyncIterator[str]:

        request_payload = self._build_payload(prompt, system_prompt)
        url = self._endpoint("streamGenerateContent")

        async with self._client.stream(
            "POST",
            url,
            json=request_payload,
            timeout=_STREAM_TIMEOUT,
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "gemini_stream: HTTP %d — %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                raise

            async for line in response.aiter_lines():
                if not line:
                    continue

                raw = line.removeprefix("data:").strip()
                if raw == "[DONE]":
                    break

                try:
                    chunk_data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("gemini_stream: skipped non-JSON line: %.120s", raw)
                    continue

                text = self._extract_text(chunk_data, context="stream")
                if text:
                    yield text



    async def _post_with_retry(
        self,
        url: str,
        payload: dict,
        timeout: httpx.Timeout, ) -> dict:
       
        delay = _RETRY_BASE_DELAY
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.post(url, json=payload, timeout=timeout)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                    logger.error(
                        "gemini_generate: HTTP %d on attempt %d/%d — %s",
                        status, attempt, _MAX_RETRIES, exc.response.text,
                    )
                    raise
                wait = min(delay, _RETRY_MAX_DELAY)
                logger.warning(
                    "gemini_generate: HTTP %d — retrying in %.1fs (attempt %d/%d)",
                    status, wait, attempt, _MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                delay *= 2
                last_exc = exc

            except httpx.TransportError as exc:
               
                if attempt == _MAX_RETRIES:
                    logger.error(
                        "gemini_generate: transport error on attempt %d/%d: %s",
                        attempt, _MAX_RETRIES, exc,
                    )
                    raise
                wait = min(delay, _RETRY_MAX_DELAY)
                logger.warning(
                    "gemini_generate: transport error — retrying in %.1fs (%s)",
                    wait, exc,
                )
                await asyncio.sleep(wait)
                delay *= 2
                last_exc = exc

        raise RuntimeError("Retry loop exited without returning") from last_exc


    def _endpoint(self, method: str) -> str:
        """Build the Gemini REST endpoint URL (no API key in the URL)."""
        return (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self._model}:{method}"
        )

    def _build_payload(self, prompt: str, system_prompt: str | None) -> dict:
        """Construct the Gemini ``generateContent`` request body."""
        payload: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self._temperature,
                **({"maxOutputTokens": self._max_tokens} if self._max_tokens else {}),
            },
        }
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        return payload

    @staticmethod
    def _extract_text(data: dict, *, context: str = "") -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("gemini[%s]: response contained no candidates", context)
            return ""

        candidate  = candidates[0]
        finish     = candidate.get("finishReason", "")

        if finish and finish not in {"STOP", ""}:
            logger.warning(
                "gemini[%s]: non-STOP finish_reason=%s — content may be incomplete "
                "or blocked. safetyRatings=%s",
                context,
                finish,
                candidate.get("safetyRatings", []),
            )

        parts = candidate.get("content", {}).get("parts", [])
        if not parts:
            logger.warning("gemini[%s]: candidate had no parts", context)
            return ""

        return "".join(part.get("text", "") for part in parts)