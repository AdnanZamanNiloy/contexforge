"""Local embedding models served through sentence-transformers.

ContextForge already depends on ``sentence-transformers`` for the reranker
(``cross-encoder/ms-marco-MiniLM-L-6-v2``), so local embeddings introduce **no
new ML framework**.  This class is the generic, configurable counterpart to
``BGEEmbedder``: it accepts any sentence-transformers model id and a device.

The model is loaded lazily on first use (and cached by the caller via the
Model Hub factory) so startup stays fast and selecting a model in the UI is the
only step the user needs to take.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from core.interfaces.embedder import Embedder

__all__ = ["LocalEmbedder"]

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"


class LocalEmbedder(Embedder):
    """sentence-transformers embedder with a selectable model and device."""

    def __init__(self, model_id: str | None = None, device: str = "auto") -> None:
        self._model_id = (model_id or _DEFAULT_MODEL).strip()
        self._device = (device or "auto").strip().lower()
        self._model = None
        self._dimension: int | None = None
        self._load_lock = asyncio.Lock()

    @property
    def dimension(self) -> int | None:
        """Vector size, available once the model has been loaded."""
        return self._dimension

    async def embed_texts(
        self,
        texts: list[str],
        input_type: Literal["document", "query"],
    ) -> list[list[float]]:
        if not texts:
            raise ValueError("LocalEmbedder received an empty text list")
        model = await self._ensure_model_loaded()
        vectors = await asyncio.to_thread(
            model.encode,
            texts,
            normalize_embeddings=True,
        )
        result = [list(map(float, vec)) for vec in vectors]
        if result:
            self._dimension = len(result[0])
        return result

    async def aclose(self) -> None:
        """No network client to close; retained for the Embedder contract."""

    async def _ensure_model_loaded(self):
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is not None:
                return self._model
            self._model = await asyncio.to_thread(self._load_model_sync)
        return self._model

    def _load_model_sync(self):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - optional dependency path
            logger.exception("sentence-transformers is not installed")
            raise RuntimeError(
                "Local embedding models require the sentence-transformers package."
            ) from exc

        device = None if self._device == "auto" else self._device
        logger.info("Loading local embedding model '%s' (device=%s).", self._model_id, device or "auto")
        return SentenceTransformer(self._model_id, device=device)
