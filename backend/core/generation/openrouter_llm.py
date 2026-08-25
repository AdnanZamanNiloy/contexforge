from __future__ import annotations

from app.config.settings import settings
from core.generation.openai_compat_llm import OpenAICompatLLM

__all__ = ["OpenRouterLLM"]

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterLLM(OpenAICompatLLM):
    """OpenRouter aggregator — one key, many models (`/model:free` variants)."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            model or settings.OPENROUTER_MODEL,
            api_url=_OPENROUTER_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )
