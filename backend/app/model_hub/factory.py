"""Construction of concrete LLM / embedder instances from stored model configs.

This module is the bridge between the Model Hub's persisted configuration and
the existing provider classes under ``core.generation`` / ``core.embedding``.
It deliberately reuses those classes rather than re-implementing provider
clients, so the Model Hub adds configuration, not a parallel provider system.

Only the *active* serving model(s) are instantiated.  Registered-but-inactive
models are built transiently for a "Test" action and then discarded.
"""

from __future__ import annotations

import logging
from typing import Any

from core.embedding.local_embedder import LocalEmbedder
from core.generation.base_llm import BaseLLM
from core.generation.fallback_llm import FallbackLLM
from core.generation.gemini_llm import GeminiLLM
from core.generation.openai_compat_llm import OpenAICompatLLM
from core.interfaces.embedder import Embedder

__all__ = ["ModelHubError", "build_embedder", "build_llm", "build_llm_from_configs"]

logger = logging.getLogger(__name__)

# Providers that are served through the shared OpenAI-compatible client.
_OPENAI_COMPAT_PROVIDERS = {
    "openai",
    "together",
    "mistral",
    "deepseek",
    "custom",
    "api",
    "groq",
    "openrouter",
    "cerebras",
    "nvidia",
}
_LLM_PROVIDER_CLASSES = _OPENAI_COMPAT_PROVIDERS  # retained name for readability

# Well-known chat-completion endpoints, so a user only has to supply a Base URL
# for providers we don't know.  Kept local to the factory to avoid importing
# schema constants into the runtime layer.
_DEFAULT_CHAT_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}


class ModelHubError(RuntimeError):
    """Raised when a stored model config cannot be turned into a runtime object."""


def _require(value: Any, message: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ModelHubError(message)
    return value


def build_llm(config: dict[str, Any]) -> BaseLLM:
    """Build a single LLM provider from a stored model config.

    The config carries the *plaintext* API key only transiently (in memory):
    the route/service layer never returns it, and it is not logged here.
    """
    runtime = config.get("runtime", "api")
    model_id = _require(config.get("model_id"), "model_id is required")
    provider = (config.get("provider") or "custom").lower()

    if runtime == "local":
        from core.generation.local_llm import LocalLLM

        return LocalLLM(
            model_path=model_id,
            device=config.get("device") or "auto",
        )

    api_key = config.get("api_key") or ""

    # Google Gemini uses its own REST shape; everything else (including the
    # known OpenAI-compatible providers) shares one client so a registered key
    # can be injected uniformly.
    if provider in {"google", "gemini"}:
        return GeminiLLM(model=model_id) if not api_key else _build_gemini(model_id, api_key)

    if provider in _LLM_PROVIDER_CLASSES or provider in _OPENAI_COMPAT_PROVIDERS:
        return _build_openai_compat(
            model_id,
            api_key,
            config.get("base_url"),
            provider=provider,
        )

    raise ModelHubError(f"Unknown LLM provider: {provider}")


def _build_gemini(model_id: str, api_key: str) -> BaseLLM:
    """Build a Gemini client with a Model-Hub-supplied key.

    The existing :class:`GeminiLLM` reads its key from settings, so a
    custom-key instance is created by supplying a pre-configured httpx client
    with the ``x-goog-api-key`` header.
    """
    import httpx

    from core.generation.gemini_llm import _GENERATE_TIMEOUT, GeminiLLM

    client = httpx.AsyncClient(
        headers={"x-goog-api-key": api_key},
        timeout=_GENERATE_TIMEOUT,
    )
    return GeminiLLM(model=model_id, http_client=client)


def _build_openai_compat(
    model_id: str,
    api_key: str,
    base_url: str | None,
    *,
    provider: str,
) -> OpenAICompatLLM:
    """Build a generic OpenAI-compatible chat client for an arbitrary endpoint."""
    if not base_url:
        base_url = _DEFAULT_CHAT_URLS.get(provider)
    if not base_url:
        raise ModelHubError("A Base URL is required for this provider.")
    return OpenAICompatLLM(
        model=model_id,
        api_url=_chat_url(base_url),
        api_key=api_key or "not-required",
    )


def _chat_url(base_url: str) -> str:
    """Normalise a Base URL to a chat-completions endpoint.

    Accepts either a full endpoint (``.../chat/completions``), a ``/v1`` base,
    or a bare host, appending the well-known suffix as needed.
    """
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def build_llm_from_configs(configs: list[dict[str, Any]], *, name: str | None = None) -> FallbackLLM:
    """Build a ``FallbackLLM`` chain from an ordered list of model configs."""
    if not configs:
        raise ModelHubError("A chain requires at least one model.")
    providers = [build_llm(cfg) for cfg in configs]
    llm = FallbackLLM(providers=providers)
    if name:
        # FallbackLLM's display model is derived from its providers; keep the
        # chain name available for logging without changing its behaviour.
        logger.debug("Built LLM chain '%s' with %d provider(s).", name, len(providers))
    return llm


def build_embedder(config: dict[str, Any]) -> Embedder:
    """Build an embedding client from a stored model config."""
    runtime = config.get("runtime", "api")
    model_id = _require(config.get("model_id"), "model_id is required")

    if runtime == "local":
        return LocalEmbedder(
            model_id=model_id,
            device=config.get("device") or "auto",
        )

    provider = (config.get("provider") or "voyage").lower()
    api_key = config.get("api_key") or ""

    if provider == "voyage":
        from core.embedding.voyage_embedder import VoyageEmbedder

        return VoyageEmbedder(cache_path=None, api_key=api_key or None, model=model_id)

    if provider in {"openai", "custom", "api", "together", "mistral", "deepseek"}:
        from core.embedding.openai_compat_embedder import OpenAICompatEmbedder

        base_url = config.get("base_url")
        if not base_url:
            base_url = "https://api.openai.com/v1"
        return OpenAICompatEmbedder(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
        )

    raise ModelHubError(f"Unknown embedding provider: {provider}")
