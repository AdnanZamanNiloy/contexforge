from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Literal

import httpx

from app.config.settings import settings
from core.interfaces.embedder import Embedder
from observability.tracer import observe

__all__ = ["VoyageEmbedder"]

logger = logging.getLogger(__name__)

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


_MAX_RETRIES = 12
_RETRY_BASE_DELAY = 1.0   # seconds; jitters and grows toward a ceiling
_RETRY_MAX_DELAY = 20.0   # seconds; capped so a long 429 window can be waited out
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MIN_REQUEST_INTERVAL = 21.0  # seconds; stay under Voyage's 3 RPM free tier
_MAX_TOKENS_PER_REQUEST = 8000  # estimate; stay under Voyage's 10K TPM free tier


def _estimate_tokens(text: str) -> int:
    """Rough token estimate — Voyage tokenizer is ~4 chars/token for code."""
    return max(1, len(text) // 4)


def _batch_size(texts: List[str], configured: int) -> int:
    """Shrink *configured* to the largest count whose token estimate fits the budget."""
    if not texts:
        return configured
    total_tokens = sum(_estimate_tokens(t) for t in texts)
    if total_tokens == 0:
        return configured
    by_budget = max(1, _MAX_TOKENS_PER_REQUEST * len(texts) // total_tokens)
    return max(1, min(configured, by_budget))


def _cache_key(text: str, input_type: str) -> str:
    normalised = unicodedata.normalize("NFC", text).encode("utf-8")
    digest = hashlib.blake2b(normalised, digest_size=32).hexdigest()
    return f"{input_type}:{digest}"


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Return the numeric ``Retry-After`` hint, or ``None`` when absent/invalid."""
    header = response.headers.get("retry-after")
    if not header:
        return None
    try:
        return float(header)
    except (TypeError, ValueError):
        return None


def _validate_texts(texts: List[str]) -> None:
    if not texts:
        raise ValueError("VoyageEmbedder received an empty text list")
    for idx, text in enumerate(texts):
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"VoyageEmbedder received empty or non-string text at index {idx}"
            )



class VoyageEmbedder(Embedder):

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path: Path = Path(cache_path or settings.CACHE_PATH)
        self._cache: Dict[str, List[float]] = {}
        self._cache_loaded = False
        self._dirty = False 
        self._load_lock = asyncio.Lock()

        # Voyage's unpaid tier is limited to 3 requests/minute.  We must not
        # send the next request until a full interval has elapsed, otherwise the
        # provider 429s and all our retry budget is wasted.
        self._last_request_at: float = 0.0
        self._request_lock = asyncio.Lock()

        self._client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {settings.VOYAGE_API_KEY}",
                "Content-Type": "application/json",
            },
        )


    # Public API
    @observe(name="embed_texts")
    async def embed_texts(
        self,
        texts: List[str],
        input_type: Literal["document", "query"],
    ) -> List[List[float]]:
        _validate_texts(texts)
        await self._ensure_cache_loaded()

        # Partition texts into cache hits and misses
        result: List[List[float]] = [[] for _ in range(len(texts))]
        missing_texts: List[str] = []
        missing_indices: List[int] = []

        for idx, text in enumerate(texts):
            key = _cache_key(text, input_type)
            if key in self._cache:
                result[idx] = self._cache[key]
            else:
                missing_texts.append(text)
                missing_indices.append(idx)

        # Fetch missing texts from Voyage in batches, sized by token budget so a
        # single request stays under Voyage's 10K TPM ceiling, and throttled so
        # consecutive requests respect the 3 RPM ceiling.
        if missing_texts:
            batch_size = _batch_size(missing_texts, settings.VOYAGE_BATCH_SIZE)
            fetched_vectors: List[List[float]] = []

            for start in range(0, len(missing_texts), batch_size):
                batch = missing_texts[start : start + batch_size]
                vectors = await self._embed_batch(batch, input_type)

                if len(vectors) != len(batch):
                    raise ValueError(
                        f"Voyage API returned {len(vectors)} vectors for a batch of "
                        f"{len(batch)} texts — response is incomplete"
                    )
                fetched_vectors.extend(vectors)

                # Persist as we go: a 429 later in the run must not lose the
                # embeddings already fetched, otherwise the caller re-embeds the
                # whole text list on every retry and can never make progress
                # while the provider is rate-limiting its request window.
                for idx, vector in zip(
                    missing_indices[start : start + len(batch)], vectors
                ):
                    key = _cache_key(texts[idx], input_type)
                    self._cache[key] = vector
                    result[idx] = vector
                await self._save_cache()

            self._dirty = True

        if self._dirty:
            await self._save_cache()
            self._dirty = False

        logger.debug(
            "embed_texts: %d total, %d cache hits, %d fetched from API.",
            len(texts),
            len(texts) - len(missing_texts),
            len(missing_texts),
        )
        return result

    async def aclose(self) -> None:
        await self._client.aclose()



    async def _embed_batch(
        self,
        texts: List[str],
        input_type: Literal["document", "query"],
    ) -> List[List[float]]:

        payload = {
            "model": settings.VOYAGE_MODEL,
            "input": texts,
            "input_type": input_type,
        }
        delay = _RETRY_BASE_DELAY
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._throttled_request(payload)

                if response.status_code in _RETRY_STATUS:
                    last_status = response.status_code
                    service_delay = _retry_after_seconds(response)
                    if service_delay is not None:
                        delay = service_delay
                    else:
                        # Grow toward the ceiling and add jitter so concurrent
                        # callers do not re-synchronise onto the same window.
                        jitter = random.uniform(0, delay * 0.5)
                        delay = min(_RETRY_MAX_DELAY, delay * 2) + jitter
                    logger.warning(
                        "Voyage API returned %d on attempt %d/%d — retrying in %.1fs",
                        response.status_code, attempt, _MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                data = response.json()
                return [item["embedding"] for item in data.get("data", [])]

            except httpx.TransportError as exc:
                last_exc = exc
                jitter = random.uniform(0, delay * 0.5)
                delay = min(_RETRY_MAX_DELAY, delay * 2) + jitter
                logger.warning(
                    "Voyage transport error on attempt %d/%d: %s — retrying in %.1fs",
                    attempt, _MAX_RETRIES, exc, delay,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Voyage API failed after {_MAX_RETRIES} attempts"
        ) from last_exc



    async def _throttled_request(self, payload: dict) -> httpx.Response:
        """POST *payload*, waiting out the free-tier 3 RPM window first.

        The throttle is shared across all concurrent callers through an instance
        lock, so a batch of sub-requests never re-synchronises onto Voyage's
        per-minute window and trips the 429 limit.
        """
        async with self._request_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if self._last_request_at and elapsed < _MIN_REQUEST_INTERVAL:
                wait = _MIN_REQUEST_INTERVAL - elapsed
                logger.debug(
                    "Voyage throttle: waiting %.1fs before next request.", wait,
                )
                await asyncio.sleep(wait)
            response = await self._client.post(_VOYAGE_URL, json=payload)
            self._last_request_at = time.monotonic()
            return response

    async def _ensure_cache_loaded(self) -> None:
        async with self._load_lock:
            if self._cache_loaded:
                return
            await asyncio.to_thread(self._load_cache_sync)
            self._cache_loaded = True



    def _load_cache_sync(self) -> None:

        if not self._cache_path.exists():
            logger.debug("No embedding cache found at %s — starting fresh.", self._cache_path)
            return
        try:
            content = self._cache_path.read_text(encoding="utf-8")
            if content.strip():
                self._cache = json.loads(content)
                logger.debug("Loaded %d cached embeddings from %s.", len(self._cache), self._cache_path)
        except json.JSONDecodeError as exc:

            logger.error(
                "Embedding cache at %s is corrupt (%s) — starting with empty cache.",
                self._cache_path, exc,
            )
            self._cache = {}
        except OSError as exc:
            logger.error("Could not read embedding cache: %s", exc)
            self._cache = {}

    async def _save_cache(self) -> None:
        await asyncio.to_thread(self._save_cache_sync)


    def _save_cache_sync(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._cache, separators=(",", ":")),
                encoding="utf-8",
            )
            logger.debug("Saved %d embeddings to cache at %s.", len(self._cache), self._cache_path)
        except OSError as exc:
            logger.error("Failed to save embedding cache: %s", exc)

