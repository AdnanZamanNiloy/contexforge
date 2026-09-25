"""Sentinels used when no Model Hub serving selection is active.

ContextForge's model selection is owned entirely by the Model Hub.  When the
user has not yet chosen a served LLM or embedding model, the pipeline must not
silently fall back to environment-driven providers — it must surface a clear,
actionable error telling the user to configure the Model Hub.

These sentinels implement the existing ``LLM`` / ``Embedder`` interfaces so they
slot into the orchestrator without any type gymnastics, but every operation
raises ``NotConfiguredError``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal

from core.interfaces.embedder import Embedder
from core.interfaces.llm import LLM

__all__ = ["NotConfiguredError", "NullEmbedder", "NullLLM"]

_NO_LLM = (
    "No LLM model is being served. Open the Model Hub, add an LLM model, "
    "and select it under Serving."
)
_NO_EMBEDDER = (
    "No embedding model is being served. Open the Model Hub, add an embedding "
    "model, and select it under Serving."
)


class NotConfiguredError(RuntimeError):
    """Raised when a pipeline operation needs a model that is not served."""


class NullLLM(LLM):
    """LLM placeholder that fails loudly until a model is served."""

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        raise NotConfiguredError(_NO_LLM)

    async def stream(self, prompt: str, system_prompt: str | None = None) -> AsyncIterator[str]:
        raise NotConfiguredError(_NO_LLM)
        yield ""  # pragma: no cover - unreachable, makes this an async generator


class NullEmbedder(Embedder):
    """Embedder placeholder that fails loudly until a model is served."""

    async def embed_texts(
        self,
        texts: list[str],
        input_type: Literal["document", "query"],
    ) -> list[list[float]]:
        raise NotConfiguredError(_NO_EMBEDDER)

    async def aclose(self) -> None:
        return None
