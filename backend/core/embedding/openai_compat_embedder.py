"""OpenAI-compatible embedding endpoint client.

Covers OpenAI and any provider exposing ``POST {base_url}/embeddings`` with the
standard ``{"data": [{"embedding": [...]}]}`` response shape.  Uses the same
httpx-based approach as the existing Voyage embedder, with retry-on-transient
status handling, and introduces no new dependency.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import httpx

from core.interfaces.embedder import Embedder

__all__ = ["OpenAICompatEmbedder"]

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.0
_RETRY_MAX_DELAY = 16.0
_TIMEOUT = httpx.Timeout(timeout=60.0)


class OpenAICompatEmbedder(Embedder):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not model or not model.strip():
            raise ValueError("OpenAICompatEmbedder requires a model id")
        if not base_url or not base_url.strip():
            raise ValueError("OpenAICompatEmbedder requires a base URL")
        self._model = model.strip()
        self._api_key = api_key or ""
        self._endpoint = self._embeddings_url(base_url)
        self._client = http_client or httpx.AsyncClient(timeout=_TIMEOUT)

    async def embed_texts(
        self,
        texts: list[str],
        input_type: Literal["document", "query"],
    ) -> list[list[float]]:
        if not texts:
            raise ValueError("OpenAICompatEmbedder received an empty text list")
        for idx, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"OpenAICompatEmbedder received empty text at index {idx}")

        payload = {"model": self._model, "input": texts}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        delay = _RETRY_BASE_DELAY
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.post(self._endpoint, json=payload, headers=headers)
                if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    logger.warning(
                        "embedding endpoint returned %d on attempt %d/%d — retrying.",
                        response.status_code,
                        attempt,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(min(delay, _RETRY_MAX_DELAY))
                    delay *= 2
                    continue
                response.raise_for_status()
                data = response.json()
                return [item["embedding"] for item in data.get("data", [])]
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES:
                    raise
                await asyncio.sleep(min(delay, _RETRY_MAX_DELAY))
                delay *= 2
        raise RuntimeError(f"Embedding endpoint failed after {_MAX_RETRIES} attempts") from last_exc

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _embeddings_url(base_url: str) -> str:
        url = base_url.rstrip("/")
        if url.endswith("/embeddings"):
            return url
        if url.endswith("/v1"):
            return f"{url}/embeddings"
        return f"{url}/v1/embeddings"
