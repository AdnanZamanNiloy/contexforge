"""Local LLM execution via a local OpenAI-compatible server.

ContextForge does not embed an LLM inference runtime (that would add a heavy,
GPU-only ML stack the project deliberately avoids).  "Local" LLMs are therefore
served by a user-run OpenAI-compatible server — llama.cpp's ``llama-server``,
Ollama, vLLM, LM Studio, etc. — all of which expose
``POST /v1/chat/completions``.

This class reuses :class:`OpenAICompatLLM` for all request building, retry and
SSE handling, so local and API models share one battle-tested transport.  The
default endpoint targets a llama.cpp server on ``127.0.0.1:8080``.
"""

from __future__ import annotations

from typing import Any

from core.generation.openai_compat_llm import OpenAICompatLLM

__all__ = ["LocalLLM"]

_DEFAULT_LOCAL_URL = "http://127.0.0.1:8080/v1/chat/completions"


class LocalLLM(OpenAICompatLLM):
    """Chat client for a locally hosted OpenAI-compatible server.

    ``model_path`` is passed as the model id to the local server (llama.cpp
    accepts the loaded model's alias or any label); ``device`` is accepted for
    configuration parity and surfaced to the user, but device placement is
    decided by the local server rather than by ContextForge.
    """

    def __init__(
        self,
        model_path: str,
        *,
        device: str = "auto",
        api_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        http_client: Any | None = None,
    ) -> None:
        self.device = device or "auto"
        super().__init__(
            model_path,
            api_url=api_url or _DEFAULT_LOCAL_URL,
            # Local servers do not authenticate; OpenAICompatLLM rejects an
            # empty key, so pass a placeholder that is never transmitted as a
            # real credential.
            api_key="local",
            temperature=temperature,
            max_tokens=max_tokens,
            http_client=http_client,
        )
