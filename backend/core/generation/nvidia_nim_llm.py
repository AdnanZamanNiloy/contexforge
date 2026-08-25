from __future__ import annotations

from app.config.settings import settings
from core.generation.openai_compat_llm import OpenAICompatLLM

__all__ = ["NvidiaNimLLM"]

_NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


class NvidiaNimLLM(OpenAICompatLLM):
    """NVIDIA NIM — free OpenAI-compatible integrated API (build.nvidia.com)."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            model or settings.NVIDIA_MODEL,
            api_url=_NVIDIA_NIM_URL,
            api_key=settings.NVIDIA_API_KEY,
        )
