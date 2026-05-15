from __future__ import annotations

import asyncio
import logging
from typing import List, Literal

from core.interfaces.embedder import Embedder


logger = logging.getLogger(__name__)


class BGEEmbedder(Embedder):
    """Optional local embedder. Only enable explicitly."""

    def __init__(self) -> None:
        self._model = None

    async def embed_texts(
        self, texts: List[str], input_type: Literal["document", "query"]
    ) -> List[List[float]]:
        await self._ensure_model_loaded()
        if self._model is None:
            raise RuntimeError("BGE model not available")
        return await asyncio.to_thread(self._model.encode, texts, normalize_embeddings=True)

    async def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        await asyncio.to_thread(self._load_model_sync)

    def _load_model_sync(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            logger.exception("sentence-transformers not installed")
            raise RuntimeError("BGE embedder requires sentence-transformers") from exc
        self._model = SentenceTransformer("BAAI/bge-base-en-v1.5")
