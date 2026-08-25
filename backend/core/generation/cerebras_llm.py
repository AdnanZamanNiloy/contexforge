from __future__ import annotations

from app.config.settings import settings
from core.generation.openai_compat_llm import OpenAICompatLLM

__all__ = ["CerebrasLLM"]

_CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"


class CerebrasLLM(OpenAICompatLLM):
    """Cerebras Inference — very fast free tier for open models."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            model or settings.CEREBRAS_MODEL,
            api_url=_CEREBRAS_URL,
            api_key=settings.CEREBRAS_API_KEY,
        )
